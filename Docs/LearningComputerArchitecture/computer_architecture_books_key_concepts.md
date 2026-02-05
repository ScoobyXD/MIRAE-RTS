# Computer Architecture: Top 3 Modern Books & Key Concepts

## Overview
This document presents the three best modern computer architecture books (published 2017-2022) and their comprehensive key concepts and sub-concepts. These books represent the current state-of-the-art in computer architecture education.

---

## Book 1: Digital Design and Computer Architecture (RISC-V Edition, 2021)
**Authors:** David Harris & Sarah Harris  
**Publisher:** Morgan Kaufmann/Elsevier  
**Edition:** RISC-V Edition (2021) / ARM Edition / 2nd Edition  
**Target Audience:** Students and professionals learning digital design and computer architecture

### Book Philosophy
- Bottom-up approach: from digital logic gates to complete processor design
- Hands-on methodology with HDL implementations (SystemVerilog and VHDL)
- Build-your-own microprocessor approach
- Engaging, humorous writing style with practical examples

### Main Key Concepts & Sub-Concepts

#### 1. **Digital Logic Fundamentals (From Zero to One)**
   - **Number Systems**
     - Binary representation
     - Hexadecimal notation
     - Signed and unsigned numbers
     - Two's complement arithmetic
   - **Boolean Algebra**
     - Logic gates (AND, OR, NOT, NAND, NOR, XOR, XNOR)
     - Boolean expressions and truth tables
     - De Morgan's laws
     - Logic minimization
   - **Transistors and CMOS Technology**
     - MOSFET operation
     - CMOS logic circuits
     - Power consumption
     - Propagation delay

#### 2. **Combinational Logic Design**
   - **Combinational Building Blocks**
     - Multiplexers and demultiplexers
     - Decoders and encoders
     - Priority circuits
   - **Arithmetic Circuits**
     - Half adders and full adders
     - Ripple-carry adders
     - Carry-lookahead adders
     - Subtractors and comparators
     - ALU (Arithmetic Logic Unit) design
   - **Timing Analysis**
     - Critical path
     - Setup and hold times
     - Clock skew
     - Glitches and hazards

#### 3. **Sequential Logic Design**
   - **Latches and Flip-Flops**
     - SR latch
     - D latch and D flip-flop
     - Register design
     - Edge-triggered vs. level-sensitive
   - **Finite State Machines (FSMs)**
     - Moore machines
     - Mealy machines
     - State diagrams and state tables
     - FSM design methodology
   - **Timing and Clocking**
     - Synchronous design principles
     - Clock period calculation
     - Metastability
     - Reset strategies

#### 4. **Hardware Description Languages (HDLs)**
   - **SystemVerilog**
     - Module syntax and hierarchy
     - Combinational logic modeling
     - Sequential logic modeling
     - Testbench development
     - Simulation and synthesis
   - **VHDL**
     - Entity and architecture
     - Signal declarations
     - Concurrent and sequential statements
     - Packages and libraries
   - **Design Methodology**
     - Behavioral vs. structural modeling
     - Synthesis considerations
     - FPGA implementation

#### 5. **Digital Building Blocks**
   - **Memory Arrays**
     - RAM (Random Access Memory)
     - ROM (Read-Only Memory)
     - Register files
     - Memory hierarchy concepts
   - **Logic Arrays**
     - Programmable Logic Arrays (PLAs)
     - Field-Programmable Gate Arrays (FPGAs)
   - **Sequential Building Blocks**
     - Counters
     - Shift registers
     - Timing circuits

#### 6. **Computer Architecture (Instruction Set Architecture)**
   - **RISC-V ISA**
     - Instruction formats (R-type, I-type, S-type, B-type, U-type, J-type)
     - Register set (32 general-purpose registers)
     - Addressing modes
     - Assembly language programming
   - **Processor Organization**
     - Datapath components
     - Control unit design
     - Program counter and instruction memory
   - **Memory Architecture**
     - Von Neumann vs. Harvard architecture
     - Memory-mapped I/O
     - Byte addressing and alignment

#### 7. **Microarchitecture**
   - **Single-Cycle Processor**
     - Datapath design
     - Control unit logic
     - Performance analysis (CPI = 1)
   - **Multicycle Processor**
     - FSM-based control
     - Instruction execution stages
     - Performance improvements
   - **Pipelined Processor**
     - Five-stage pipeline (Fetch, Decode, Execute, Memory, Writeback)
     - Pipeline registers
     - Hazards and forwarding
     - Branch prediction
     - Performance optimization

#### 8. **Memory Systems**
   - **Cache Memory**
     - Cache organization (direct-mapped, set-associative, fully associative)
     - Cache replacement policies (LRU, random)
     - Write policies (write-through, write-back)
     - Cache performance metrics (hit rate, miss penalty)
   - **Virtual Memory**
     - Paging and page tables
     - Translation Lookaside Buffer (TLB)
     - Address translation
     - Memory protection
   - **Memory Hierarchy**
     - Locality principles (temporal and spatial)
     - Multi-level caches
     - Main memory (DRAM)
     - Secondary storage

#### 9. **I/O Systems**
   - **I/O Interfacing**
     - Memory-mapped I/O vs. port-mapped I/O
     - Polling vs. interrupts
     - Direct Memory Access (DMA)
   - **Peripheral Communication**
     - UART (RS-232)
     - SPI (Serial Peripheral Interface)
     - I2C bus
     - USB interface
   - **Practical Examples**
     - LCD interfacing
     - Motor control
     - Wireless communication
     - Analog-to-digital conversion

#### 10. **Advanced Topics**
   - **Parallel Processing**
     - Instruction-level parallelism
     - Thread-level parallelism
     - Data-level parallelism
   - **Modern I/O Systems**
     - PCIe (PCI Express)
     - SDRAM and DDR memory
     - WiFi interfaces
     - High-speed serial communications

---

## Book 2: Computer Architecture: A Quantitative Approach (6th Edition, 2017)
**Authors:** John L. Hennessy & David A. Patterson (2017 Turing Award Winners)  
**Publisher:** Morgan Kaufmann  
**Edition:** 6th Edition (2017)  
**Target Audience:** Graduate students, professional architects, and advanced practitioners

### Book Philosophy
- Quantitative, data-driven approach to architecture decisions
- Focus on performance measurement and optimization
- Real-world examples from modern processors
- Emphasis on design trade-offs and cost-benefit analysis

### Main Key Concepts & Sub-Concepts

#### 1. **Fundamentals of Quantitative Design and Analysis**
   - **Performance Metrics**
     - Execution time and throughput
     - CPU performance equation: Time = Instructions × CPI × Clock cycle time
     - Speedup and efficiency
     - Amdahl's Law
     - Benchmarking methodologies (SPEC, TPC)
   - **Cost-Performance Trade-offs**
     - Cost models
     - Price/performance ratio
     - Total cost of ownership
   - **Quantitative Principles**
     - Make the common case fast
     - Parallelism exploitation
     - Principle of locality
     - Focus on bottlenecks
   - **Trends and Technology**
     - Moore's Law and scaling
     - Dennard scaling
     - Power wall
     - Memory wall
     - ILP wall

#### 2. **Memory Hierarchy Design**
   - **Cache Design**
     - Cache organization principles
     - Block size optimization
     - Associativity trade-offs
     - Replacement policies (LRU, LFU, optimal)
     - Write strategies (write-allocate, no-write-allocate)
   - **Advanced Cache Techniques**
     - Multi-level cache hierarchies (L1, L2, L3)
     - Victim caches
     - Prefetching strategies (hardware and software)
     - Non-blocking caches
     - Critical word first and early restart
   - **Virtual Memory**
     - TLB organization and optimization
     - Page table structures (hierarchical, inverted)
     - Page size selection
     - Huge pages and superpages
   - **Memory Technologies**
     - SRAM vs. DRAM
     - DDR SDRAM evolution (DDR3, DDR4, DDR5)
     - Emerging memory technologies (3D XPoint, HBM)
   - **Cache Coherence**
     - Snooping protocols
     - Directory-based protocols
     - MESI, MOESI protocols

#### 3. **Instruction-Level Parallelism (ILP)**
   - **Basic ILP Concepts**
     - Instruction dependencies (data, control, structural)
     - Dynamic scheduling fundamentals
     - Tomasulo's algorithm
     - Reorder buffer (ROB)
   - **Branch Prediction**
     - Static prediction strategies
     - Dynamic predictors (1-bit, 2-bit, correlating)
     - Tournament predictors
     - Branch target buffers (BTB)
     - Return address stack
   - **Superscalar Execution**
     - Multiple issue (static vs. dynamic)
     - Out-of-order execution
     - Register renaming
     - Speculation and recovery
   - **VLIW and EPIC**
     - Very Long Instruction Word architectures
     - Explicitly Parallel Instruction Computing
     - Compiler techniques for ILP
     - Predication and speculation
   - **ILP Limitations**
     - Window size constraints
     - Branch misprediction penalties
     - Memory latency hiding
     - Power consumption issues

#### 4. **Data-Level Parallelism**
   - **Vector Architectures**
     - Vector registers and operations
     - Vector length and stride
     - Chaining and chimes
     - Conditional execution in vectors
   - **SIMD Extensions**
     - x86 SIMD evolution (MMX, SSE, AVX, AVX-512)
     - ARM NEON
     - Multimedia instructions
   - **Graphics Processing Units (GPUs)**
     - GPU architecture fundamentals
     - CUDA and OpenCL programming models
     - Warps and thread blocks
     - Memory hierarchy in GPUs
     - Compute vs. graphics applications
   - **Deep Learning Accelerators**
     - Tensor cores
     - Systolic arrays
     - Domain-specific architectures for AI

#### 5. **Thread-Level Parallelism (TLP)**
   - **Multiprocessor Architectures**
     - Symmetric multiprocessing (SMP)
     - Uniform vs. non-uniform memory access (UMA vs. NUMA)
     - Cache coherence protocols at scale
   - **Multithreading**
     - Fine-grained multithreading
     - Coarse-grained multithreading
     - Simultaneous multithreading (SMT/Hyper-Threading)
     - Hardware thread scheduling
   - **Synchronization**
     - Atomic operations
     - Locks and lock-free programming
     - Barriers and semaphores
     - Memory consistency models
   - **Interconnection Networks**
     - Bus-based systems
     - Crossbar switches
     - Multistage networks
     - Topology choices (mesh, torus, hypercube)
     - Network-on-chip (NoC)

#### 6. **Warehouse-Scale Computing**
   - **WSC Architecture**
     - Google's warehouse-scale computer design
     - Server architecture
     - Network topology at scale
     - Storage systems (GFS, Colossus)
   - **Cost Modeling**
     - Total cost of ownership for datacenters
     - Power usage effectiveness (PUE)
     - Energy proportionality
   - **Programming Frameworks**
     - MapReduce and Hadoop
     - Spark and distributed computing
     - Workload characterization
   - **Failure Management**
     - Redundancy strategies
     - Fault tolerance mechanisms
     - Graceful degradation

#### 7. **Domain-Specific Architectures (DSAs)**
   - **Motivation for DSAs**
     - End of general-purpose scaling
     - Specialization benefits
     - Performance vs. flexibility trade-offs
   - **Deep Neural Network Accelerators**
     - TPU (Tensor Processing Unit) architecture
     - Systolic array design
     - Reduced precision arithmetic
   - **Guidelines for DSAs**
     - Identify key operations
     - Optimize memory hierarchy
     - Leverage sparsity and structured operations
     - Co-design with algorithms

#### 8. **Memory and Storage** reading this right now as of 2/2/2026 
   - **Main Memory Systems**
     - DRAM organization
     - Memory controller design
     - Memory scheduling algorithms
     - Error correction codes (ECC)
   - **Storage Technologies**
     - Hard disk drives (HDDs)
     - Solid-state drives (SSDs)
     - NVMe interface
     - Storage arrays and RAID
   - **Reliability and Dependability**
     - Mean time to failure (MTTF)
     - Availability metrics
     - Redundancy techniques

#### 9. **Request-Level Parallelism**
   - **Load Balancing**
     - Request distribution strategies
     - Server pools
   - **Latency Hiding**
     - Asynchronous I/O
     - Queuing theory application
   - **Scalability**
     - Horizontal vs. vertical scaling
     - Microservices architecture

---

## Book 3: Modern Computer Architecture and Organization (2nd Edition, 2022)
**Author:** Jim Ledin  
**Publisher:** Packt Publishing  
**Edition:** 2nd Edition (2022)  
**Target Audience:** Software developers, computer science students, and engineers

### Book Philosophy
- Practical, hands-on approach to modern computer systems
- Focus on current processor architectures (x86, ARM, RISC-V)
- Integration of emerging topics (quantum computing, blockchain, cybersecurity)
- Emphasis on real-world applications and devices

### Main Key Concepts & Sub-Concepts

#### 1. **Digital Circuitry Foundations**
   - **Transistor Technology**
     - Semiconductor physics basics
     - MOSFET operation
     - CMOS logic
     - Power and performance characteristics
   - **Logic Gates**
     - Gate-level design
     - Logic families (TTL, CMOS)
     - Propagation delay and fan-out
   - **Sequential Logic**
     - Flip-flops and registers
     - Counters and timers
     - State machines

#### 2. **Processor Fundamentals**
   - **Instruction Sets**
     - RISC vs. CISC philosophies
     - Instruction encoding
     - Addressing modes
     - Assembly language basics
   - **Processor Pipeline**
     - Pipeline stages
     - Hazard detection and resolution
     - Branch prediction strategies
   - **Performance Optimization**
     - Superscalar execution
     - Out-of-order execution
     - Speculative execution

#### 3. **x86 Architecture**
   - **x86 Evolution**
     - 8086 to modern x86-64
     - Backward compatibility
     - Legacy support implications
   - **x86 Instruction Set**
     - Intel instruction set architecture
     - Register organization
     - Segmentation and protected mode
     - SIMD instructions (SSE, AVX)
   - **x86 Microarchitecture**
     - Modern Intel processors (Core, Xeon)
     - AMD Ryzen architecture
     - Cache hierarchies
     - Integrated memory controllers
   - **x86 in PCs**
     - Desktop and laptop implementations
     - Thermal management
     - Power states

#### 4. **ARM Architecture**
   - **ARM Fundamentals**
     - ARM processor family overview
     - Load-store architecture
     - Conditional execution
   - **ARM Instruction Sets**
     - ARM (32-bit)
     - Thumb and Thumb-2
     - ARM64 (AArch64)
   - **ARM Cortex Series**
     - Cortex-A (Application processors)
     - Cortex-R (Real-time processors)
     - Cortex-M (Microcontroller processors)
   - **ARM in Mobile Devices**
     - Smartphone SoCs (Snapdragon, Apple Silicon)
     - Power efficiency techniques
     - big.LITTLE architecture
     - Heterogeneous computing

#### 5. **RISC-V Architecture**
   - **RISC-V Philosophy**
     - Open-source ISA
     - Modular design
     - Extensibility
   - **RISC-V Base ISA**
     - RV32I and RV64I
     - Register organization
     - Instruction formats
   - **RISC-V Extensions**
     - Multiply/Divide (M)
     - Atomic (A)
     - Floating-point (F, D)
     - Compressed (C)
     - Vector (V)
   - **RISC-V Implementations**
     - Open-source cores (BOOM, Rocket)
     - Commercial implementations
     - FPGA prototyping

#### 6. **Processor Architectures for Smartphones**
   - **Mobile SoC Design**
     - System-on-Chip integration
     - Power management
     - Thermal constraints
   - **Components Integration**
     - CPU clusters
     - GPU
     - DSP (Digital Signal Processor)
     - ISP (Image Signal Processor)
     - Neural processing units (NPU)
   - **Connectivity**
     - Cellular modems (4G, 5G)
     - WiFi and Bluetooth
     - NFC
   - **Examples**
     - Qualcomm Snapdragon
     - Apple A-series and M-series
     - Samsung Exynos

#### 7. **PC and Server Architecture**
   - **Desktop Computer Organization**
     - Motherboard architecture
     - Chipsets (Northbridge/Southbridge concepts)
     - Expansion buses (PCIe)
   - **Server-Specific Features**
     - Multi-socket systems
     - Error-correcting memory
     - Reliability, availability, serviceability (RAS)
     - Hardware redundancy
   - **Form Factors**
     - ATX, Mini-ITX
     - Rack-mount servers
     - Blade servers

#### 8. **Cloud Server Architecture**
   - **Datacenter Computing**
     - Server rack organization
     - Power and cooling infrastructure
     - Network topology
   - **Virtualization**
     - Hypervisor architecture
     - Hardware-assisted virtualization (VT-x, AMD-V)
     - Container technology
   - **Cloud-Specific Optimizations**
     - High-density servers
     - Energy efficiency
     - Scalability

#### 9. **Memory Systems in Modern Computers**
   - **Memory Technologies**
     - SRAM, DRAM, Flash
     - DDR4 and DDR5
     - LPDDR for mobile
     - HBM (High Bandwidth Memory)
   - **Memory Hierarchy**
     - Cache levels and organization
     - Main memory architecture
     - Non-volatile storage (SSD, NVMe)
   - **Memory Controllers**
     - Integrated vs. discrete
     - Channel organization
     - Bandwidth optimization

#### 10. **Input/Output and Peripherals**
   - **I/O Interfaces**
     - USB (2.0, 3.x, 4.0, USB-C)
     - Thunderbolt
     - DisplayPort and HDMI
     - Serial interfaces (UART, SPI, I2C)
   - **Peripheral Communication**
     - Polling vs. interrupts
     - DMA (Direct Memory Access)
     - I/O virtualization
   - **Storage Interfaces**
     - SATA
     - NVMe/PCIe
     - UFS (Universal Flash Storage)

#### 11. **Quantum Computing**
   - **Quantum Fundamentals**
     - Qubits and superposition
     - Quantum gates
     - Entanglement
     - Quantum measurement
   - **Quantum Computer Architecture**
     - Quantum processor design
     - Error correction
     - Decoherence and noise
   - **Programming Quantum Computers**
     - Quantum algorithms (Shor's, Grover's)
     - Quantum software frameworks (Qiskit, Cirq)
     - Near-term applications
   - **Current State**
     - IBM Q, Google Sycamore
     - D-Wave quantum annealing
     - Limitations and challenges

#### 12. **Blockchain and Cryptocurrency Mining**
   - **Blockchain Basics**
     - Distributed ledger technology
     - Consensus mechanisms (Proof of Work, Proof of Stake)
     - Hash functions and cryptography
   - **Mining Hardware**
     - CPU mining
     - GPU mining
     - ASIC miners
     - FPGA implementations
   - **Architecture Implications**
     - Parallelization strategies
     - Power efficiency
     - Hash rate optimization

#### 13. **Self-Driving Vehicle Computing**
   - **Autonomous Vehicle Architecture**
     - Sensor suite (cameras, LIDAR, radar)
     - Compute platforms
     - Real-time processing requirements
   - **Processing Demands**
     - Computer vision
     - Machine learning inference
     - Sensor fusion
     - Path planning
   - **Hardware Solutions**
     - NVIDIA Drive platform
     - Tesla FSD computer
     - Mobileye EyeQ
   - **Safety and Redundancy**
     - Fail-safe systems
     - Redundant processing
     - Functional safety standards (ISO 26262)

#### 14. **Cybersecurity in Computer Architecture**
   - **Hardware Security Features**
     - Secure boot
     - Trusted Platform Module (TPM)
     - Hardware encryption (AES-NI)
     - Secure enclaves (Intel SGX, ARM TrustZone)
   - **Attack Vectors**
     - Side-channel attacks
     - Spectre and Meltdown vulnerabilities
     - Row hammer attacks
     - Rowhammer and other DRAM exploits
   - **Security Mitigations**
     - Address space layout randomization (ASLR)
     - Control flow integrity
     - Memory tagging
     - Microcode updates
   - **Penetration Testing**
     - Hardware vulnerability assessment
     - Firmware security
     - Supply chain security

#### 15. **FPGA Implementation**
   - **FPGA Basics**
     - Configurable logic blocks
     - Routing architecture
     - I/O blocks
   - **RISC-V on FPGA**
     - Soft processor cores
     - Hardware acceleration
     - Custom instruction extensions
   - **Design Tools**
     - Synthesis and place-and-route
     - Timing analysis
     - Hardware debugging

#### 16. **Future Directions**
   - **Emerging Technologies**
     - Neuromorphic computing
     - Photonic computing
     - DNA computing
   - **Architecture Trends**
     - Chiplets and disaggregated processors
     - 3D stacking
     - Advanced packaging
   - **Challenges**
     - Power density limits
     - Memory bandwidth walls
     - Programming complexity

---

## Comparison and Complementary Nature of the Books

### Harris & Harris (Digital Design and Computer Architecture)
- **Strength:** Bottom-up, hands-on approach; excellent for beginners
- **Focus:** Learning by building (actual processor design)
- **Depth:** Fundamental to intermediate
- **Best for:** Students, first-time learners, practical implementation

### Hennessy & Patterson (Computer Architecture: A Quantitative Approach)
- **Strength:** Quantitative, research-based, comprehensive
- **Focus:** Performance analysis and optimization principles
- **Depth:** Advanced, graduate-level
- **Best for:** Professional architects, researchers, advanced students

### Jim Ledin (Modern Computer Architecture and Organization)
- **Strength:** Contemporary coverage of current systems
- **Focus:** Practical knowledge of modern architectures (x86, ARM, RISC-V)
- **Depth:** Intermediate with breadth across domains
- **Best for:** Software developers wanting hardware knowledge, practical engineers

### Learning Path Recommendation
1. **Start with:** Harris & Harris (build foundation and understanding)
2. **Progress to:** Jim Ledin (gain breadth in modern systems)
3. **Advance with:** Hennessy & Patterson (master performance optimization and advanced concepts)

---

## Additional Resources

### Online Materials
- Harris & Harris companion website: Lecture slides, HDL code, labs
- Hennessy & Patterson: Historical perspectives, appendices, problem solutions
- Jim Ledin GitHub: Code examples and projects

### Key Takeaways Across All Books
1. **Performance = Instructions × CPI × Clock Cycle Time**
2. **Make the common case fast**
3. **Exploit parallelism at all levels (ILP, TLP, DLP)**
4. **Memory hierarchy is critical to performance**
5. **Power is now the primary constraint**
6. **Specialization (DSAs) is the future**
7. **Security must be designed into hardware**
8. **RISC-V represents the democratization of processor design**

---

## Conclusion

These three books provide comprehensive coverage of computer architecture from fundamentals to cutting-edge topics. Together, they offer:

- **Practical Skills:** Design and implement processors
- **Theoretical Understanding:** Performance modeling and optimization
- **Contemporary Knowledge:** Modern architectures and emerging technologies
- **Career Preparation:** Interview readiness for roles at companies like Apex Space

For someone with your background in C++ and embedded systems (STM32), I particularly recommend starting with Harris & Harris for HDL skills, then moving to Ledin for breadth in ARM/RISC-V, and finally to Hennessy & Patterson for deep architectural principles relevant to satellite systems.

---

*Document prepared: February 2026*  
*Based on current editions as of 2022*
