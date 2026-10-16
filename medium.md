# Deep Dive into Models and ModelJars.org

If you've been following my recent articles outlining my vision for AI in Java, it starts with doing as much as possible in the JVM, keeping your application data private and only sending information over the wire when there is no other option around. Leveraging your local compute, and avoiving paying tokens to "Big AI" when not necessary.
To fullfil that vision on the JVM, I started by giving myself the best foundation to deal with the lingua franca of AI… Vectors, a library to store, search, and doing math on the arrays of numbers models use to represent information. See the article https://medium.com/@bsbodden_68805/deep-dive-into-the-vectors-library-2f774d816d58?sharedUserId=bsbodden_68805 
Models is a Java library for infenrence in the JVM. It loads model weights, tokenizes text, executes the model's computation, and exposes the result through Java APIs. ModelJars.org supplies the other half of the experience: which exact artifact are we loading, where do its files come from, and what evidence says it can do the job?
The result is three layers with different responsibilities. Vectors supplies numerical building blocks and searchable collections. Models builds inference on those building blocks. ModelJars.org builds verified model identity and task-specific loading on Models. 
Models
Models supports AI models in the following formats: 
GGUF files which typically bundle model configuration, tokenizer metadata, and compressed weights into a single artifact
Hugging Face Safetensors bundles which keep configuration and tokenizer files alongside one or more weight files
CACT format a specialized format used by Needle 2. 

Loading a supported model means reading its configuration, initializing its tokenizer, and mapping its weights into the Java process's address space. Memory mapping lets the runtime access large weight files without copying them wholesale into the JVM heap. Models then connects those tensors to its implementation of the model's architecture.

Inference happens inside the application process. For text generation, Models turns the prompt into tokens, processes them through the model's layers, and retains the attention cache or recurrent state needed to continue the conversation. It then selects an output token, feeds it back into the model, and repeats until generation finishes, optionally streaming the text as it goes. The Java backend executes the model using numerical operations from the Vectors library alongside Models' own implementations built on the JDK's Vector API. Optional acceleration replaces selected operations with native CPU kernels written in Rust, or with Rust kernels compiled to PTX for compatible NVIDIA GPUs. Both paths use Java's Foreign Function and Memory API to reach native code; model execution, tokenization, sampling, and the generation loop remain coordinated in Java.

## Why do we need Rust?

Models evaluates performance at the application boundary: how long a user waits for the first token, how quickly the remaining tokens arrive, and how long the complete request takes. Our thresholds distinguish a model that runs correctly from one that feels responsive on the tested hardware.
For standalone text generation, the benchmark uses these limits. TTFT is time to first token; TPOT is time per output token after generation starts. p95 is the 95th percentile, so these limits account for slower trials rather than just the average.

Classification requires at least ten trials and every trial to succeed. The separate decode-throughput comparison labels at least 80% of the same artifact's llama.cpp throughput competitive, at least 50% viable, and anything lower needs optimization. These are the standalone benchmark's classifications, not the catalog admission rules. 

For retrieval-augmented generation, the complete pipeline has a separate set of limits:
All four limits must pass for the corresponding tier. A correct pipeline that exceeds the usable limits receives performance-reduced status. Qualification also requires quality: retrieval recall of at least 95%; reciprocal rank, fact coverage, citation recall, citation precision, and answer correctness of at least 90%; and correct abstention on every applicable case. The model itself must contribute answers on at least one-third of attempts, with at least 90% of those answers correct. An extractive fallback cannot substitute for that model contribution. 

RAG qualification additionally compares the same model artifact on the same host under matching prompts, context, threads, and generation settings. Against the authoritative Ollama or Transformers baseline, Models must deliver at least 80% of median decode throughput and take no more than 1.5 times the p95 end-to-end latency. A reviewed, artifact-specific publisher reference uses those same limits. The ordinary llama.cpp comparison has a 45% throughput floor and a 2-times latency ceiling, but passing that comparison alone cannot qualify a model under the standard policy. A performance-reduced model can still qualify if it passes the quality, contribution, and relative gates; its slower absolute tier remains visible. 

## How the Rust shims work

A shim is a small implementation of a particular numerical operation that Java can call. Models keeps model loading, tokenization, the computation graph, state ownership, sampling, and generation in Java. When the graph reaches an eligible operation, such as multiplying packed model weights by an activation vector, it can dispatch that operation to our Rust library through Java's Foreign Function and Memory API. The result returns to the same Java pipeline.

The CPU library ships inside a platform-specific JAR. Java checks its identity, integrity, and binary interface, loads it, and checks the capabilities it exposes. Mapped weight segments and reusable native workspaces let the kernels operate without expanding the entire checkpoint into heap objects. Models runs inference in Java, with optional Rust shims that accelerate selected calculations while Java handles the rest.

There are two Rust modules: the CPU kernels and the CUDA kernels. CUDA kernels are compiled to PTX, NVIDIA's device instruction representation. Java calls the NVIDIA driver through FFM to load and launch them and manage device resources. Both modules implement selected operations within Models' pipeline. Apple's Foundation Models integration is separate: its bridge is written in Swift and delegates to Apple's system-managed model. 

Rust gives these kernels direct access to CPU intrinsics and a device compilation path. The relevant question for a Java replacement is whether the supported JVM can generate an equally effective instruction sequence while preserving the arithmetic contract. Some gaps involve compiler lowering; others are implementation work we can do in Java already. The Vector API's available operators are the starting point, but API availability alone does not establish generated-code performance.

## The shims and their removal conditions

The entries below group related functions by purpose. Several capabilities share the same native library, worker pool, and arithmetic; they are not separate inference engines. 

### 1. Q4_0, Q5_0, and Q8_0 projections

These kernels multiply weights stored in compact integer blocks by quantized activations. Rust unpacks the weights and uses CPU-specific integer dot-product sequences: AVX2 multiply-and-add instructions on x86, and NEON dot-product instructions on eligible ARM hosts. The JVM challenge is consistently lowering widening, signedness conversion, multiplication, and accumulation into comparably compact machine code. Java can express the arithmetic; the unresolved requirement is predictable performance across the supported CPUs and model shapes.
**Removal condition:** Java projections preserve the existing numerical contract and match the retained route's measured performance for single-token decode and batched prefill on each affected host. That may come from better Java expressions, improved HotSpot recognition, or additional vector operations. No particular future JDK release is a promised prerequisite. [CPU kernels](../../projects/models/backend-native/src/main/rust/model-kernels/src/lib.rs), [ARM kernels](../../projects/models/backend-native/src/main/rust/model-kernels/src/neon.rs).

### 2. Q4_K, Q5_K, and Q6_K projections

K-quant formats combine packed weights with sub-block scales and, for some formats, minimum corrections. The native kernels specialize the unpacking and integer accumulation for each layout. Their challenge is the combined sequence: bit extraction, scale handling, activation preparation, register use, and accumulation must all remain efficient. Mixed-format grouped calls also share activation preparation between compatible matrices.
**Removal condition:** Java matches those sequences and their memory behavior without losing the existing numerical contract or whole-model performance. Efficient integer dot products help, but a faster multiplication instruction alone cannot retire a kernel whose unpacking or memory traffic still dominates. [Format-specific implementations](../../projects/models/backend-native/src/main/rust/model-kernels/src/lib.rs).

### 3. Q5_1 projections

Q5_1 carries a block minimum that makes its arithmetic different from the centered formats. This shim dequantizes weights and multiplies by floating-point activations, following Java's fixed accumulation order. It deliberately keeps certain multiply/add steps unfused to preserve the result. There is no grouped Q5_1 route. The retained experiment shows improvements for several matrix shapes, a slower mean for one small batch, and **no demonstrated end-to-end improvement on short embedding probes**.
**Removal condition:** a Java implementation matches the useful measured cases while preserving exact results. No missing JVM feature has been established as an unavoidable blocker here; loop structure, conversion, compiler behavior, and scheduling must be measured. The short-probe null result prevents claiming that this shim is necessary for every embedding workload. [Arithmetic contract and paired measurements](../../projects/models/benchmark-results/2026–10–08-q5–1-rust-shim/NOTES.md).

### 4. PTQ1_0 ternary projections

The Bonsai path stores weights as packed ternary values: minus one, zero, and one. The shim decodes those values, multiplies them by Q8 activations, and applies scales in a fixed order. It has scalar, x86 AVX2, and ARM NEON implementations. Java retains the model's signed Hadamard transforms, recurrent state, and graph. This implementation is part of the ongoing Bonsai qualification work; its presence does not by itself establish production qualification.
**Removal condition:** Java matches the unpacking and integer dot-product throughput on the affected hosts while preserving activation rounding, half-precision scale rounding, and the final floating-point accumulation order. The relevant JVM constraint is efficient lowering of that combined packed-arithmetic sequence. Java already has a SIMD implementation, so replacement is a measured comparison rather than waiting for Java to gain ternary arithmetic. [PTQ kernels and parity tests](../../projects/models/backend-native/src/main/rust/model-kernels/src/ptq.rs).

### 5. Activation preparation and half-precision scale conversion

These are supporting routines inside the projection shims. They prepare reusable quantized activations and convert compact scale values for arithmetic. Native code can use hardware conversion instructions in the surrounding kernel. Java already provides `Float.float16ToFloat` and `Float.floatToFloat16`; half-precision conversion itself is not missing. [Java conversion API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Float.html#float16ToFloat(short)).
**Removal condition:** Java produces the same activation bytes and scale values with equivalent conversion, allocation, and overall projection costs. Any remaining gap needs evidence from the actual compiled loop. These helpers disappear with their last native caller rather than requiring a separate backend migration. [Native preparation and conversion routines](../../projects/models/backend-native/src/main/rust/model-kernels/src/lib.rs).

### 6. Persistent workers and grouped dispatch

Generating one token involves many short matrix operations. The native pool keeps workers alive, partitions work, and uses bounded polling before parking. Grouped and independent batch dispatch can submit several operations through one synchronization round. Java supports persistent platform threads and synchronization already; the issue is the cost of the particular dispatch implementation. Competing Java and Rust pools can also waste CPU by polling simultaneously, which the native integration explicitly avoids.
**Removal condition:** Java scheduling matches dispatch latency, sustained throughput, CPU consumption, and resource cleanup for both small decode jobs and larger prefill batches. This can be implementation work on an existing JVM. There is no established requirement to wait for a new threading API. [Worker implementation](../../projects/models/backend-native/src/main/rust/model-kernels/src/lib.rs), [Java pool coordination](../../projects/models/backend-native/src/main/java/com/integrallis/models/backend/nativekernel/RustGgufBatchedMatrixKernel.java).

### 7. Batched weight reuse and vector accumulation

These paths reuse unpacked weight blocks across multiple input rows and keep partial sums in registers. They reduce repeated decoding and memory reads during prefill. Java can implement the same loop organization; the performance question is whether compilation preserves that reuse without excessive register spills or temporary allocations. Exported capabilities do not force routing: grouped Q5_0, for example, is deliberately excluded by the dispatcher because its measured behavior did not justify selecting it.
**Removal condition:** equivalent Java batching passes the arithmetic checks and matches the native route's latency and allocation behavior across the relevant batch sizes. A new JVM feature is not inherently required. [Batching implementation](../../projects/models/backend-native/src/main/rust/model-kernels/src/lib.rs), [grouping decisions](../../projects/models/backend-native/src/main/java/com/integrallis/models/backend/nativekernel/RustGgufBatchedMatrixKernel.java).

### 8. CPU grouped-query attention

This kernel calculates attention scores over cached keys, normalizes them with softmax, and combines cached values for the query heads. It uses floating-point arithmetic and supports the cache spans passed by Java. Its benefit depends on vectorized loops, memory access, reductions, and scheduling. There is no demonstrated missing Java arithmetic operation that makes this kernel intrinsically native.
**Removal condition:** Java attention matches performance while preserving the required output behavior across context lengths, head layouts, and shared-prefix cache cases. Floating-point reduction order matters: a small numerical change can select a different next token. A replacement needs tensor and token checks, not only a tolerance-based microbenchmark. [Native attention](../../projects/models/backend-native/src/main/rust/model-kernels/src/lib.rs), [Java attention](../../projects/models/backend-java/src/main/java/com/integrallis/models/backend/purejava/ops/GroupedQueryAttentionKernel.java).

### 9. Gated DeltaNet recurrence: retained experiment, not an active shim

The native library contains sequential and grouped recurrence operations, but the production dispatcher returns `false` for both capabilities. Java already performs this work. The native recurrence's tolerance-based checks do not establish identical generated output, and its retained timing comparison does not establish a speed advantage over Java.
**Removal condition:** no JVM advancement is needed to stop depending on these operations, because production does not select them. Deleting the experimental implementation is a separate maintenance decision after checking its callers, tests, and binary compatibility. It must not be presented as a necessary performance shim. [Explicit routing decisions and rationale](../../projects/models/backend-native/src/main/java/com/integrallis/models/backend/nativekernel/RustGgufBatchedMatrixKernel.java).

### 10. CUDA Q4_K and Q6_K projections

The GPU module exports separate `models_q4k_decode_projection` and `models_q6k_decode_projection` kernels. They distribute supported packed matrix operations across NVIDIA GPU threads. Java's CPU Vector API does not provide this device execution path; Models supplies Rust-to-PTX compilation and reaches the driver through FFM.
**Removal condition:** a supported Java-based device implementation can compile and run equivalent kernels, manage transfers and device memory, and match correctness and whole-model performance including startup. This removes the Rust kernel source dependency; it does not remove the need for a GPU driver. Babylon's code-reflection and HAT work offers an avenue to investigate, but it is not a promised replacement or delivery date. [GPU exports](../../projects/models/backend-cuda/src/main/rust/models-cuda-kernels/src/device.rs), [OpenJDK Babylon](https://github.com/openjdk/babylon).

### 11. CUDA grouped-query decode attention

The third GPU export, `models_gqa_decode_attention`, runs supported single-token attention on the device. Java retains cache ownership and controls eligibility; unsupported cache arrangements use the CPU path. Keeping projections fast while repeatedly moving attention data can erase a GPU gain, so the full pipeline must be measured.

**Removal condition:** the Java-based GPU path also handles attention reductions, softmax, cache layout, transfers, and fallback behavior with equivalent numerical and application-level results. A Java-to-GPU compiler alone is insufficient without that runtime integration. [CUDA routing and resource handling](../../projects/models/backend-cuda/src/main/java/com/integrallis/models/backend/cuda/CudaGgufBatchedMatrixKernel.java), [device attention](../../projects/models/backend-cuda/src/main/rust/models-cuda-kernels/src/attention.rs).

## What actually authorizes removal

Retirement proceeds one operation and supported configuration at a time: implement the Java candidate, check its numerical contract and real-model outputs, compare both routes on the same host, and repeat the affected workload qualifications. Measure cold and warm behavior, memory, and the complete request as well as the kernel. A promising Java candidate can still fail on another batch size, architecture, or compiler state.

Once the Java route passes the declared criteria, update the runtime selection and verify the released artifacts. Delete the native implementation when no supported configuration needs it. Future JVM capabilities can make that work easier; passing measurements are what make removal justified. [Retirement policy](../../projects/models/docs/content/modules/ROOT/pages/architecture.adoc).