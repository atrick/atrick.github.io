---
layout: default
title:  UnsafeRawPointer API for In-Memory Layout
categories: proposal
date: 2016-06-04
---
# UnsafeRawPointer API for In-Memory Layout

* Proposal: [SE-NNNN](https://github.com/atrick/swift-evolution/blob/voidpointer/proposals/XXXX-unsaferawpointer.md)
* Author(s): [Andrew Trick](https://github.com/atrick)
* Status: **[Awaiting review](#rationale)**
* Review manager: TBD

1. [Introduction](#introduction)
2. [Proposed Solution](#proposed-solution)
3. [Motivation](#motivation)
4. [Detailed design](#detailed-design)
5. [Impact on existing code](#impact-on-existing-code)
6. [Implementation status](#implementation-status)
7. [Future improvements and planned additive API](#future-improvements-and-planned-additive-API)
8. [Variations under consideration](#variations-under-consideration)
8. [Alternatives previously considered](#alternatives-previously-considered)

## Introduction

Swift enforces type safe access to memory and follows strict aliasing
rules. However, code that uses unsafe APIs or imported types can
circumvent the language's natural type safety. Consider the following
example of *type punning* using the ``UnsafePointer`` type::

```swift
  let ptrT = UnsafeMutablePointer<T>(allocatingCapacity: 1)
  // Store T at this address.
  ptrT[0] = T()
  // Load U at this address
  let u = UnsafePointer<U>(ptrT)[0]
```

This code violates assumptions made by the compiler and falls into the
category of "undefined behavior". Undefined behavior is a way of
saying that we cannot easily specify constraints on the behavior of
programs that violate a rule. The program may crash, corrupt memory,
or be miscompiled in other ways. Miscompilation may include optimizing
away code that was expected to execute or executing code that was not
expected to execute.

Swift already protects against undefined behavior as long as the code
does not use "unsafe" constructs. However, UnsafePointer is an
important API for interoperability and building high performance data
structures. As such, the rules for safe, well-defined usage of the API
should be clear. Currently, it is too easy to use UnsafePointer
improperly. For example, innocuous argument conversion such as this
could lead to undefined behavior:

```swift
func takesUIntPtr(_ p: UnsafeMutablePointer<UInt>) -> UInt {
  return p[0]
}
func takesIntPtr(q: UnsafeMutablePointer<Int>) -> UInt {
  return takesUIntPtr(UnsafeMutablePointer(q))
}

```

Furthermore, no API currently exists for accessing raw, untyped
memory. `UnsafePointer<Pointee>` and `UnsafeMutablePointer<Pointee>`
refer to a typed region of memory, and the compiler assumes that the
element type (`Pointee`) is consistent with other access to the same
memory. For details of the compiler's rules for memory aliasing,
[proposed Type Safe Memory Access documentation][1]. Making
`UnsafePointer` safer requires introducing a new pointer type that is
not bound by the same strict aliasing rules.

This proposal aims to achieve several goals in one coherent design:

1. Provide an untyped pointer type.
 
2. Specify which pointer types follow strict aliasing rules.

3. Inhibit UnsafePointer conversion that violates strict aliasing.

4. Provide an API for safe type punning (memcpy semantics).

5. Provide an API for manual memory layout (bytewise pointer arithmetic).

Early swift-evolution thread: [\[RFC\] UnsafeBytePointer API for In-Memory Layout](https://lists.swift.org/pipermail/swift-evolution/Week-of-Mon-20160509/thread.html#16909)

[1]:https://github.com/atrick/swift/blob/type-safe-mem-docs/docs/TypeSafeMemory.rst

Mentions of `UnsafePointer` that appear in this document's prose also
apply to `UnsafeMutablePointer`.

## Proposed Solution

We first introduce each aspect of the proposed API so that the Motivation section can show examples. The Detailed design section lists
the complete API.

### UnsafeRawPointer

New `UnsafeRawPointer` and `UnsafeMutableRawPointer` types will
represent a "raw" untyped memory region. Raw memory is what is
returned from memory allocation prior to initialization. Normally,
once the memory has been initialized, it will be accessed via a typed
`UnsafeMutablePointer`. After initialization, the raw memory can still
be accessed as a sequence of bytes, but the raw API provides no
information about the initialized type. Because the raw pointer may
alias with any type, the semantics of reading and writing through a
raw pointer are similar to C `memcpy`.

### Memory allocation and initialization

`UnsafeMutableRawPointer` will provide an `allocatingCapacity`
initializer and `deallocate` method:

```swift
extension UnsafeMutableRawPointer {
    // Allocate memory with the size and alignment of 'allocatingCapacity'
    // contiguous elements of 'T'. The resulting 'self' pointer is not
    // associated with the type 'T'. The type is only provided as a convenient
    // way to derive stride and alignment.
    init<T>(allocatingCapacity: Int, of: T.Type)

    func deallocate<T>(capacity: Int, of: T.Type)
```

Initializing memory at an `UnsafeMutableRawPointer` produces an
`UnsafeMutablePointer<Pointee>` and deinitializing the
`UnsafeMutablePointer<Pointee>` produces an `UnsafeMutableRawPointer`.

```swift
extension UnsafeMutableRawPointer {
  // Copy a value of type 'T' into this uninitialized memory.
  // Returns an UnsafeMutablePointer into the newly initialized memory.
  //
  // Precondition: memory is uninitialized.
  func initialize<T>(_: T.Type, with: T) -> UnsafeMutablePointer<T>
}

extension UnsafeMutablePointer {
  /// De-initialize the `count` `Pointee`s starting at `self`, returning
  /// their memory to an uninitialized state.
  /// Returns a raw pointer to the uninitialized memory.
  public func deinitialize(count: Int = 1) -> UnsafeMutableRawPointer
}
```

### Raw memory access

Loading from and storing to memory via an `Unsafe[Mutable]RawPointer`
is safe independent of the type of value being loaded or stored and
independent of the memory's allocated type as long as layout
guarantees are met (per the ABI), and care is taken to properly
initialize and deinitialize values that contain managed
references. This allows legal type punning within Swift and allows
Swift code to access a common region of memory that may be shared
across an external interface that does not provide type safety
guarantees.

Accessing type punned memory directly through a designated
`Unsafe[Mutable]RawPointer` type provides sound basis for compiler
implementation of strict aliasing. This is in contrast with the
approach of simply providing a special unsafe pointer cast operation
for bypassing type safety, which cannot be reliably implemented.

```swift
extension UnsafeMutableRawPointer {
  // Read raw bytes and construct a value of type `T`.
  func load<T>(_: T.Type) -> T
  
  // Write a value of type 'T' into this memory, overwriting any
  // previous values.
  //
  // Note that this is not an assignment, because any previously
  // initialized value in this memory is not deinitialized.
  //
  // Precondition: memory is either uninitialized or initialized with a
  // trivial type.
  //
  // Precondition: 'T' is a trivial type.
  func storeRaw<T>(_: T.Type, from: T)
}
```

### Bytewise pointer arithmetic

Providing an API for accessing raw memory would not serve much purpose
without the ability to compute byte offsets. This API is identical for `UnsafeRawPointer` and `UnsafeMutableRawPointer`.

```swift
extension UnsafeRawPointer : Strideable {
  public func distance(to : UnsafeRawPointer) -> Int

  public func advanced(by : Int) -> UnsafeRawPointer
}

public func == (lhs: UnsafeRawPointer, rhs: UnsafeRawPointer) -> Bool

public func < (lhs: UnsafeRawPointer, rhs: UnsafeRawPointer) -> Bool

public func + (lhs: Int, rhs: UnsafeRawPointer) -> UnsafeRawPointer

public func - (lhs: UnsafeRawPointer, rhs: UnsafeRawPointer) -> Int
```

### Unsafe pointer conversion

Currently, an `UnsafePointer` initializer supports conversion between potentially incompatible pointer types:

```swift
struct UnsafePointer<Pointee> {
  public init<U>(_ from : UnsafePointer<U>)
}
```

This initializer will be removed. To perform an unsafe cast to a typed
pointer, the user will be required to construct an `UnsafeRawPointer`
and invoke a method that explicitly takes the destination type:

```swift
extension UnsafeRawPointer {
  func toType<T>(_: T.Type) -> UnsafePointer<T> {
}
```

## Motivation

### Memory model motivation

The following examples show the differences between memory access as it currently would be done using `UnsafeMutablePointer` vs. the proposed `UnsafeMutableRawPointer`.

Consider two layout compatible, but unrelated structs, and helpers that write to and read from these structs via unsafe pointers:

```swift
struct A {
  var value: Int
}

struct B {
  var value: Int
}

func assignA(_ pA: UnsafeMutablePointer<A>) {
  pA[0] = A(value:42)
}

func assignB(_ pB: UnsafeMutablePointer<B>) {
  pB[0] = B(value:13)
}

func printA(_ pA: UnsafePointer<A>) {
  print(pA[0])
}

func printB(_ pB: UnsafePointer<B>) {
  print(pB[0])
}
```

Normal allocation, initialization, access, and deinitialization of a struct looks like this with `UnsafePointer`:

```swift
func testNormal() {
  // Memory is uninitialized, but 'pA' is already typed, which is a lie.
  let pA = UnsafeMutablePointer<A>(allocatingCapacity: 1)

  // Assignment without initialization is a misuse of the API, but
  // happens to work because A contains no managed references.
  assignA(pA)

  printA(pA)

  pA.deinitialize(count: 1)
  pA.deallocateCapacity(1)
}

```

With `UnsafeMutableRawPointer`, the distinction between initialized and
uninitialized memory is now clear. This may seem dogmatic, but becomes
important when writing generic code:

```swift
func initA(p: UnsafeMutableRawPointer) -> UnsafeMutablePointer<A> {
  p.initialize(A.self, with: A(value:42))
}

func initB(p: UnsafeMutableRawPointer) -> UnsafeMutablePointer<B> {
  p.initialize(B.self, with: B(value:13))
}
```

```swift
func testNormal() {
  let newp = UnsafeMutableRawPointer(allocatingCapacity: 1, of: A.self)

  // assignA cannot be called on newp. This forces initialization:
  let pA = initA(newp)

  printA(pA)

  let uninitp = pA.deinitialize(count: 1)
  uninitp.deallocate(capacity: 1, of: A.self)
}
```

Technically, it is correct to initialize values of type `A` and `B` in
different memory locations, but confusing and dangerous with the
current `UnsafeMutablePointer` API:

```swift
// Return a pointer to (A, B).
func initAB() -> UnsafeMutablePointer<A> {

  // Memory is uninitialized, but 'pA' is already typed.
  let pA = UnsafeMutablePointer<A>(allocatingCapacity: 2)

  assignA(UnsafeMutablePointer(pA))

  // pA is recast as pB with no indication that the pointee type has changed!
  assignB(UnsafeMutablePointer(pA + 1))
  return pA
}
```
```swift
// Code in the caller is confusing:
do {
  let pA = initAB()
  printA(pA)

  // pA is again recast as pB with no indication that the pointee type changes!
  printB(UnsafeMutablePointer(pA + 1))

  // Or recast to pB first, which is also misleading!
  printB(UnsafeMutablePointer<B>(pA) + 1)
}
```

With `UnsafeMutableRawPointer`, raw memory may have the correct size and
alignment for a type, but does not have a type until it is
initialized. Unsafe conversion between raw memory and typed memory is
always explicit:

```swift
// Return a pointer to an untyped memory region initialized with (A, B).
func initAB() -> UnsafeMutableRawPointer {

  // Allocate raw memory of size 2 x strideof(Int).
  let p = UnsafeMutableRawPointer(allocatingCapacity: 2, of: Int.self)

  // Initialize the first Int with A.
  let pA = initA(p)

  // Initialize the second Int with B.
  initB(pA + 1)

  return p
}
```
```swift
// Code in the caller is explicit:
do {
  let p = initAB()

  // The untyped memory is explicitly converted to a pointer-to-A.
  // Safe because we know the underlying memory is initialized to A.
  let pA = p.toType(A.self)
  printA(pA)

  // Converting from a pointer-to-A into a pointer-to-B requires
  // creation of an UnsafeRawPointer.
  printB(UnsafeRawPointer(pA + 1).toType(B.self))

  // Or convert the original UnsafeRawPointer into pointer-to-B.
  printB((p + strideof(Int.self)).toType(B.self))
}
```

Assigning values of different type to the same location is undefined.  The compiler can choose to ignore the order of assignment, and when the function 'initAthenB' returns the memory at 'p' may hold either 13 or 42

```swift
func initAthenB(_ p: UnsafeMutablePointer<Void>) {
  assignA(UnsafeMutablePointer(p))
  assignB(UnsafeMutablePointer(p))
}
```
```swift
// Code in the caller cannot rely on the resulting memory state:
do {
  let p = UnsafeMutablePointer<Int>(allocatingCapacity: 1)
  initAthenB(p)
  printB(UnsafeMutablePointer(p))
}
```

With the proposed API, assigning values of different types to the same
location can now be safely done by properly initializing and
deinitializing the memory through `UnsafeMutableRawPointer`. The
values may still be accessed via the same convenient
UnsafeMutablePointer type. Type punning has not happened, because the
UnsafeMutablePointer has the same type as the memory's initialized
type when it is dereferenced.

```swift
// Precondition: 'p' points to uninitialized memory.
//
// Postcondition: the raw memory holds an initialized value of B(13).
func initAthenB(_ p: UnsafeRawMutablePointer) -> UnsafeMutablePointer<B> {
  let pA = initA(p)

  // Raw memory holds an 'A' which may be accessed via 'pA'.
  // After deinitializing 'pA', 'puninit' receives a pointer to
  // untyped raw memory, which may be reused for 'B'.
  let puninit = pA.deinitialize(count: 1)

  return initB(puninit)
}
```
```swift
// Code in the caller can rely on the memory state:
do {
  let newp = UnsafeMutableRawPointer(allocatingCapacity: 1, of: Int.self)
  let pB = initAthenB(newp)
  printB(pB)
}
```

No API currently exists that allows initialized memory to hold either A or B.

```swift
// This conditional initialization looks valid, but is dangerous.
func initAorB(_ p: UnsafeMutablePointer<Void>, isA: Bool) {
  if isA {
    assignA(UnsafeMutablePointer(p))
  }
  else {
    assignB(UnsafeMutablePointer(p))
  }
}
```
```swift
// Code in the caller could produce undefined behavior:
do {
  let p = UnsafeMutablePointer<Int>(allocatingCapacity: 1)

  // If the compiler inlines, then the initialization and use of the
  // values of type 'A' and 'B' that share memory could be incorrectly
  // interleaved.
  initAorB(p, isA: true)
  printA(UnsafeMutablePointer(p))

  initAorB(p, isA: false)
  printB(UnsafeMutablePointer(p))
}
```

`UnsafeMutableRawPointer` allows initialized memory to hold either `A`
or `B`. The same `UnsafeMutableRawPointer` value can be reused across
multiple initializations and deinitializations. Unlike the previous
example, this is safe because the memory initialization is now an untyped
operation, which separates access to the distinct types.

```swift
func initAorB(_ p: UnsafeMutableRawPointer, isA: Bool) {
  if isA {
    initA(p)
  }
  else {
    initB(p)
  }
}
```
```swift
// Code in the caller is well defined:
do {
  let p = UnsafeMutableRawPointer(allocatingCapacity: 1, of: Int.self)

  initAorB(p, isA: true)
  printA(p.toType(A.self))

  initAorB(p, isA: false)
  print(p.toType(B.self))
}
```

`UnsafeMutableRawPointer` also provides a legal way to access the memory
using a different pointer type than the memory's initialized type (type
punning). The following example is safe because the memory is never
accessed via a typed `UnsafePointer`. Every read and write directly
using `UnsafeRawPointer` has untyped (memcpy) semantics.

```swift
// Code in the caller performs type punning 
do {
  let p = UnsafeMutableRawPointer(allocatingCapacity: 1, of: Int.self)

  initAorB(p, isA: true)

  // 'printB(p.toType(B.self))' would be illegal, because the a typed pointer
  // to 'B' cannot be used to access an unrelated type 'A'.
  // However, 'UnsafeMutableRawPointer.load()' is safe because the type
  // is layout compatible with 'A'.
  print(p.load(B.self))
}
```

Developer's may be forced to work with "loosely typed" APIs,
particularly for interoperability:

```swift
func readBytes(_ bytes: UnsafePointer<UInt8>) {
  // 3rd party implementation...
}
func readCStr(_ string: UnsafePointer<CChar>) {
  // 3rd party implementation...
}
```

Working with these API's exclusively using UnsafeMutablePointer leads to undefined behavior, as shown here using the current API:

```swift
func stringFromBytes(size: Int, value: UInt8) {
  let bytes = UnsafeMutablePointer<UInt8>(allocatingCapacity: size)
  bytes.initialize(with: value, count: size)

  readBytes(bytes)

  // If readCString is inlineable and compiled with strict aliasing,
  // then it could read uninitialized memory.
  readCStr(UnsafePointer(bytes))
}
```

Initializing memory with `UnsafeRawPointer` makes it legal to read
that memory regardless of the pointer type. Reading from uninitialized
memory is now prevented:

```swift
func genBuffer(size: Int, value: UInt8) {
  let buffer = UnsafeMutableRawPointer(allocatingCapacity: size, of: UInt8.self)

  // Writing the bytes using UnsafeRawPointer allows the bytes to be
  // read later as any type without violating string aliasing.
  buffer.initialize(UInt8.self, with: value, count: size)

  // All subsequent reads are guaranteed to see initialized memory.
  readBytes(buffer)

  readCStr(buffer)
}
```

It is even possible for the shared buffer to be mutable by using
`UnsafeRawPointer.initialize` or `UnsafeRawPointer.storeRaw` to
perform the writes:

```swift
func mutateBuffer(size: Int, value: UInt8) {
  let buffer = UnsafeMutableRawPointer(allocatingCapacity: size, of: UInt8.self)
  buffer.initialize(UInt8.self, with: value, count: size)
  readBytes(bytes)
  
  // Mutating the raw, untyped buffer bypasses strict aliasing rules.
  buffer.storeRaw(UInt8.self, from: getChar())

  readCStr(bytes)
}
func getChar() -> CChar) {
  // 3rd party implementation...
}
```

The side effects of illegal type punning may result in storing values
in the wrong sequence, reading uninitialized memory, or memory
corruption. It could even result in execution following code paths
that aren't expected as shown here:

```swift
func undefinedExecution() {
  let pA = UnsafeMutablePointer<A>(allocatingCapacity: 1)
  assignA(pA)
  if pA[0].value != 42 {
    // Code path should never execute...
    releaseDemons()
  }
  // This compiler may inline this, and hoist the store above the
  // previous check.
  unforeseenCode(pA)
}

func releaseDemons() {
  // Something that should never be executed...
}

func unforeseenCode(_ pA: UnsafeMutablePointer<A>) {
  // At some arbitrary point in the future, the same memory is
  // innocuously assigned to B.
  assignB(UnsafeMutablePointer(pA))
}
```

Prohibiting conversion between incompatible `UnsafePointer` types and
providing an API for raw memory access is necessary to expose the
danger of type punning at the API level and encourage safe idioms for
working with pointers.

### Memory model explanation

Formally the difference between `Unsafe[Mutable]RawPointer` and
`Unsafe[Mutable]Pointer<Pointee>` is simply that the former is used
for "untyped" memory access, and the later is used for "typed" memory
access. Let's refer to these as "raw pointers" and "typed
pointers". Because operations on raw pointers are "untyped", the
compiler cannot make assumptions about the underlying type of memory
and must be conservative. With operations on typed pointers, the
compiler can make strict assumptions about the type of the underlying
memory, which allows more aggressive optimization.

All allocated memory exists in one of two states: "uninitialized" or
"initialized". Upon initialization, memory is semantically associated
with the underlying type of it's initial value and remains associated
with that type until it is deinitialized. After deinitialization, the
memory no longer has an underlying semantic type.

As a matter of convention, raw (untyped) pointers primarily refer to
uninitialized (untyped) memory and typed pointers primarily refer to
initialized (typed) memory. This provides the most safety and clarity
by default, but is not a stricly enforced rule. After a raw pointer is
intialized, the raw pointer value remains valid and can continue to be
used to access the underlying memory in an untyped way. Conversely, a
raw pointer can be force-cast to a typed pointer without initializing
the underlying memory. When a program defies convention this way,
the programmer must be aware of the rules for working with raw memory:

#### Accessing initialized (typed) memory with a raw (untyped) pointer.

```swift
let rawPtr = UnsafeMutableRawPointer(allocatingCapacity: 1, of: SomeType.self)

let ptrToSomeType = rawPtr.initialize(SomeType.self, SomeType())

// overwrite initialized memory
rawPtr.storeRaw(AnotherType, AnotherType())
```

In this situation, the programmer takes responsibility for ensuring
size and alignment compatibility between the underlying initialized
type and the type used to access the memory via a raw pointer. This
requires some knowledge of the ABI.

Next, the programmer takes responsibility for ensuring that class
references are never formed to an unrelated object type. This is a incontravertible property of all reference values in the system.

Under these conditions loading a value from raw memory is always safe.

Storing a value into raw memory requires extra consideration. A raw
store overwrites memory contents without destroying the previous
value. This is safe provided that the initialized type of the
underlying memory is "trivial". In other words, the value may not
contain strong or weak references to class objects.

#### Accessing uninitialized memory with a typed pointer.

A raw pointer may be cast to a typed pointer, bypassing initialization:

```swift
let ptrToSomeType = rawPtr.toType(SomeType.self)
```

In performing this cast, the programmer declares responsibility for two
aspects of the managing the underlying memory:

1. tracking the memory's initialized state (usually of several
   individual contiguous elements)

2. ensuring that the underlying raw memory will only *ever* be
   initialized to the pointer's type

For example:

```swift
if !isInitializedAt(index) {
  (ptrToSomeType + index).initialize(with: Type())
}
return ptrToSomeType[index]
```

This is a useful technique for optimizing data structures that manage
storage for contiguous elements. The data structure may allocate a
buffer with extra capacity and track the initialized state of each
element position. Accessing the buffer via a typed pointer is both
more convenient and may improve performance under some conditions.

Note that initialization is now a typed operation. This means that the
compiler can aggressively optimize under the assumption that other
accesses to the same memory are performed via the same pointer type.

This caveat must be emphasized: casting uninitialized memory to a typed
pointer makes it illegal to initialize the same allocated memory as a
different type, either in the program's past or future. Consequently,
this should only be done when the programmer has control over the
allocation and deallocation of the memory and thus can guarantee that
the memory is never initialized to an unrelated type.

See the "C buffer" use case below.

### Expected use cases

#### Single value

#### C array

#### C buffer

#### reinterpret_cast

#### Untyped loads and stores

#### Manual layout of typed, aligned memory

#### Custom memory allocators

## Detailed design

### Pointer conversion details

`UnsafePointer<T>` to `UnsafeRawPointer` conversion will be provided
via an unlabeled initializer.

```swift
extension UnsafeRawPointer: _Pointer {
  init<T>(_: UnsafePointer<T>)
  init<T>(_: UnsafeMutablePointer<T>)
}
extension UnsafeMutableRawPointer: _Pointer {
  init<T>(_: UnsafeMutablePointer<T>)
}
```

Conversion from `UnsafeRawPointer` to a typed `UnsafePointer<T>`
requires invoking `UnsafeRawPointer.toType(T.Type)`, explicitly
spelling the destination type:

```swift
let p = UnsafeRawPointer(...)
let pT = p.toType(T.self)
```

Just as with `unsafeBitCast`, although the destination of the cast can
usually be inferred, we want the developer to explicitly state the
intended destination type, both because type inferrence can be
surprising, and because it's important for code comprehension.

Inferred `UnsafePointer<T>` conversion will now be statically
prohibited. Instead, unsafe conversion will need to explictly cast
through a raw pointer:

```swift
let pT = UnsafePointer<T>(...)
let pU = UnsafeRawPointer(pT).toType(U.self)
```

Some existing conversions between `UnsafePointer` types do not
convert `Pointee` types but instead coerce an
`UnsafePointer` to an `UnsafeMutablePointer`. This is no longer an
inferred conversion, but must be explicitly requested:

```swift
extension UnsafeMutablePointer {
  init(mutating from: UnsafePointer<Pointee>)
}
```

### Implicit argument conversion

Consider two C functions that take const pointers:

```C
void takesConstTPtr(const T*);
void takesConstVoidPtr(const void*);
```

Which will be imported with immutable pointer argument types:

```swift
func takesConstTPtr(_: UnsafePointer<T>)
func takesConstVoidPtr(_: UnsafeRawPointer)
```

Mutable pointers can be passed implicitly to immutable pointers.

```swift
let umptr: UnsafeMutablePointer<T>
let mrawptr: UnsafeMutableRawPointer
takesConstTPtr(umptr)
takesConstVoidPtr(mrawptr)
```

Implicit inout conversion will continue to work:

```swift
var anyT: T
takesConstTPtr(&anyT)
takesConstVoidPtr(&anyT)
```

`Array`/`String` conversion will continue to work:

```swift
let a = [T()]
takesConstTPtr(a)
takesConstVoidPtr(a)

let s = "string"
takesConstVoidPtr(s)
```

Consider two C functions that take nonconst pointers:

```C
void takesTPtr(T*);
void takesVoidPtr(void*);
```

Which will be imported with mutable pointer argument types:

```swift
func takesTPtr(_: UnsafeMutablePointer<T>)
func takesVoidPtr(_: UnsafeMutableRawPointer)
```

Implicit inout conversion will continue to work:

```swift
var anyT = T(...)
takesTPtr(&anyT)
takesVoidPtr(&any)
```

`Array`/`String` conversion to mutable pointer is still not allowed.

### Bulk copies

The following API entry points support copying or moving values between unsafe pointers.

Given values of these types:

```swift
  let uptr: UnsafePointer<T>
  let umptr: UnsafeMutablePointer<T>
  let rawptr: UnsafeRawPointer
  let mrawptr: UnsafeMutableRawPointer
```

`UnsafeRawPointer` to `UnsafeMutableRawPointer` raw copy (memcpy):

```swift
  mrawptr.storeRaw(contiguous: T.self, from: uptr, count: c)
  mrawptr.storeRawBackward(contiguous: T.self, from: uptr, count: c)
```

`UnsafePointer<T>` to `UnsafeMutableRawPointer`:

A raw copy from typed to raw memory can be done by calling `storeRaw`
and `storeRawBackward` as shown above via implicit argument conversion
from `UnsafePointer<T>` to `UnsafeRawPointer`.

Additionally, raw memory can be bulk initialized from typed memory:

```swift
  mraw.initialize(from: up, count: c)
  mraw.initializeBackward(from: up, count: c)
```

`UnsafeRawPointer` to `UnsafeMutablePointer<T>`:

No bulk conversion is currently supported from raw to typed memory.

`UnsafePointer<T>` to `UnsafeMutablePointer<T>`:

Copying between typed memory is still supported via bulk assignment
(the naming style is updated for consistency):

up -> ump
```swift
  ump.assign(from: up, count: c)
  ump.assignBackward(from: up, count: c)
  ump.moveAssign(from: up, count: c)
```

### Full UnsafeRawPointer API

TBD: Before this proposal goes up for review, I will include the
entire set of API changes with comments.

Most of the API was already presented above. For the sake of having it
in one place, a list of the expected UnsafeMutableRawPointer members
is shown below:

```swift
struct UnsafeMutableRawPointer : Strideable, Hashable, _Pointer {
  var _rawValue: Builtin.RawPointer
  var hashValue: Int

  init(_ _rawValue : Builtin.RawPointer)
  init?(bitPattern: Int)
  init?(bitPattern: UInt)
  init<T>(_: UnsafeMutablePointer<T>)
  init?<T>(_: UnsafeMutablePointer<T>?)

  init<T>(allocatingCapacity: Int, of: T.Type)
  deallocate<T>(capacity: Int, of: T.Type)

  func toType<T>(_: T.Type) -> UnsafeMutablePointer<T>

  func initialize<T>(_: T.Type, with: T) -> UnsafeMutablePointer<T>
  func initialize<T>(contiguous: T.Type, at: Int, with: T)
    -> UnsafeMutablePointer<T>
  func initialize<T>(from: UnsafePointer<T>, count: Int)
    -> UnsafeMutablePointer<T>
  func initializeBackward<T>(from: UnsafePointer<T>, count: Int)
    -> UnsafeMutablePointer<T>

  // This API is invalid if the source's underlying raw memory is reused and
  // cast to an unrelated Pointee type after being deinitialized here.
  func moveInitialize<T>(from: UnsafePointer<T>, count: Int)
    -> UnsafeMutablePointer<T>
  func moveInitializeBackward<T>(from: UnsafePointer<T>, count: Int)
    -> UnsafeMutablePointer<T>

  func load<T>(_: T.Type) -> T
  func load<T>(contiguous: T.Type, at: Int) -> T

  // T must not contain managed references.
  func storeRaw<T>(_: T.Type, from: T)
  func storeRaw<T>(contiguous: T.Type, at: Int, from: T)
  func storeRaw<T>(contiguous: T.Type, from: UnsafeRawPointer, count: Int)
  func storeRawBackward<T>(
    contiguous: T.Type, from: UnsafeRawPointer, count: Int)

  func distance(to: UnsafeRawPointer) -> Int
  func advanced(by: Int) -> UnsafeRawPointer
}
```

The relevant `UnsafeMutablePointer` members are:

```swift
extension UnsafeMutablePointer<Pointee> {
  init(mutating from: UnsafePointer<Pointee>)

  func initialize(with newValue: Pointee, count: Int = 1)
  func deinitialize(count: Int = 1) -> UnsafeMutableRawPointer

  // This API is invalid if the source's underlying raw memory is reused and
  // cast to an unrelated Pointee type after being deinitialized here.
  func moveAssignFrom(_ source: UnsafeMutablePointer<Pointee>, count: Int)
}
```

The [unsafeptr_convert branch][2] contains an implementation of a
simlar, previous design.

[2]:https://github.com/atrick/swift/commits/unsafeptr_convert

## Impact on existing code

The largest impact of this change is that `void*` and `const void*`
are imported as `UnsafeMutableRawPointer` and
`UnsafeRawPointer`. This impacts many public APIs, but with implicit
argument conversion should not affect typical uses of those APIs.

Any Swift projects that rely on type inference to convert between
`UnsafePointer` types will need to take action. The developer needs to
determine whether type punning is necessary. If so, they must migrate
to the `UnsafeRawPointer` API. Otherwise, they can work around the new
restriction by using `UnsafeRawPointer($0).toType(Pointee.self)`, and/or
adding a `mutating` label to their initializer.

The API for allocating and initializing unsafe pointer changes:

```swift
let p = UnsafeMutablePointer<T>(allocatingCapacity: num)
p.initialize(with: T())
```

becomes

```swift
let p = UnsafeMutableRawPointer(allocatingCapacity: num, of: T.self).initialize(with: T())
```

Deallocation similarly changes from:

```swift
p.deinitialize(num)
p.deallocateCapacity(num)
```

to

```swift
deallocate(p.deinitialize(num), capacity: num, of: T.self)
```

### Swift code migration

All occurrences of the type `Unsafe[Mutable]Pointer<Void>` will be automatically replaced with `Unsafe[Mutable]RawPointer`.

Initialization of the form `Unsafe[Mutable]Pointer`(p) will
automatically be replaced by `Unsafe[Mutable]RawPointer(p)` whenever
the type checker determines that is the expression's expected type.

Conversion between incompatible `Unsafe[Mutable]Pointer` values will
produce a diagnostic explaining that
`UnsafeMutableRawPointer($0).toType(T.self)` syntax is required for
unsafe conversion.

`initializeFrom(_: UnsafePointer<Pointee>, count: Int)`,
`initializeBackwardFrom(_: UnsafePointer<Pointee>, count: Int)`,
`assignFrom(_ source: Unsafe[Mutable]Pointer<Pointee>, count: Int)`,
`moveAssignFrom(_ source: Unsafe[Mutable]Pointer<Pointee>, count: Int)`

will be automatically converted to:

`initialize(from: UnsafePointer<Pointee>, count: Int)`,
`initializeBackward(from: UnsafePointer<Pointee>, count: Int)`,
`assign(from source: Unsafe[Mutable]Pointer<Pointee>, count: Int)`,
`moveAssign(from source: Unsafe[Mutable]Pointer<Pointee>, count: Int)`

### Standard library changes

Disallowing inferred `UnsafePointer` conversion requires some standard library code to use an explicit `toType(Pointee.self)` whenever the conversion may violate strict aliasing.

All occurrences of `Unsafe[Mutable]Pointer<Void>` in the standard
library are converted to `UnsafeRawPointer`. e.g. `unsafeAddress()` now
returns `UnsafeRawPointer`, not `UnsafePointer<Void>`.

Some occurrences of `Unsafe[Mutable]Pointer<Pointee>` in the standard
library are replaced with `UnsafeRawPointer`, either because the code was
playing too loosely with strict aliasing rules, or because the code
actually wanted to perform pointer arithmetic on byte-addresses.

`StringCore.baseAddress` changes from `OpaquePointer` to `UnsafeRawPointer`
because it is computing byte offsets and accessing the memory.
`OpaquePointer` is meant for bridging, but should be truly opaque; that is,
nondereferenceable and not involved in address computation.

The `StringCore` implementation does a considerable amount of casting
between different views of the `String` storage. The current
implementation already demonstrates some awareness of strict aliasing
rules. The rules are generally followed by ensuring that the `StringBuffer`
only be accessed using the appropriate `CodeUnit` within Swift
code. For interoperability and optimization, String buffers frequently
need to be cast to and from `CChar`. This is valid as long access to the
buffer from Swift is guarded by dynamic checks of the encoding
type. These unsafe, but dynamically legal conversion points will now
be labeled with `to: Pointee`.

`CoreAudio` utilities now use an `UnsafeRawPointer`.


## Implementation status

On my [unsafeptr_convert branch][2], I've made most of the necessary changes to
support the addition of `UnsafeRawPointer` and the removal of inferred
`UnsafePointer` conversion.

There are a several things going on here in order to make it possible
to build the standard library with the changes:

- A new `UnsafeRawPointer` type is defined.

- The type system imports `void*` as UnsafeRawPointer.

- The type system handles implicit conversions to UnsafeRawPointer.

- `UnsafeRawPointer` replaces both `UnsafePointer<Void>` and
  `UnsafeMutablePointer<Void>` (Recent feedback suggestes that
  `UnsafeMutablePointer` should also be introduced).

- The standard library was relying on inferred UnsafePointer
  conversion in over 100 places. Most of these conversions now either
  take an explicit label, such as `mutating` or have been rewritten.

- Several places in the standard library that were playing loosely
  with strict aliasing or doing bytewise pointer arithmetic now use
  UnsafeRawPointer instead.

- Explicit labeled `Unsafe[Mutable]Pointer` initializers are added.

- The inferred `Unsafe[Mutable]Pointer` conversion is removed.

Remaining work:

- UnsafeMutableRawPointer needs to be introduced, and we need to
  distinguish between `void*` and `const void*` import types.

- A name mangled abbreviation needs to be created for UnsafeRawPointer.

- The StringAPI tests should probably be rewritten with
  `UnsafeRawPointer`.

- The NSStringAPI utilities and tests may need to be ported to
  `UnsafeRawPointer`

- The CoreAudio utilities and tests may need to be ported to
  `UnsafeRawPointer`.

## Future improvements and planned additive API

`UnsafeRawPointer` should eventually support unaligned memory access. I
believe that we will eventually have a modifier that allows "packed"
struct members. At that time we may also want to add a "packed" flag to
`UnsafeRawPointer`'s `load` and `initialize` methods.

The following additive API will likely be considered in a follow-up proposal:

```swift
extension UnsafeMutableRawPointer {
  // load at a byte offset (instead of (rawPtr + offset).load(T.self))
  func load<T>(fromContiguous: T.Type, atByteOffset: Int) -> T
}
```

## Variations under consideration

### Freestanding `allocate`/`deallocate`

The allocation and deallocation API would be more appropriate and more
readable as global functions that operation on
UnsafeMutableRawPointer. `allocate` is not logically an initializer
because it is not a conversion and its main purpose is not simpy the
construction of an `UnsafeRawPointer`.


```swift
func allocate<T>(capacity: Int, of: T.Type) -> UnsafeMutableRawPointer

func deallocate<T>(_: UnsafeMutableRawPointer, capacity: Int, of: T.Type) {}

let rawPtr = allocate(capacity: 1, of: A.self)

deallocate(rawPtr, capacity: 1, of: A.self)
```

The only reason this was not done was to avoid introducing these names into the global namespace.

Two other alternatives worth considering are qualified global functions

```swift
let rawPtr = unsafeAllocate(capacity: 1, of: A.self)

unsafeDeallocate(rawPtr, capacity: 1, of: A.self)
```

or static methods:

```swift
let rawPtr = UnsafeMutableRawPointer.allocate(capacity: 1, of: A.self)

UnsafeMutableRawPointer.deallocate(rawPtr, capacity: 1, of: A.self)
```

### Conversion via initializer instead of `toType`

This proposal calls for unsafe pointer type conversion to be performed via an `UnsafeRawPointer.toType` method as in:

```swift
rawptr.toType(A.self)
```

However, conversions are customarily done via an initializer, such as:

```swift
UnsafePointer(rawptr, to: A.self)
```

Conversion via initialization is generally a good convention, but
there are reasons not to use an initializer in this case. Conversion
via initializer indicates a normal, expected operation on the type
that is safe or at least checked. (e.g. integer initialization may
narrow, but traps on truncation). UnsafePointer is already "unsafe" in
the sense that it's lifetime is not automatically managed, but its
initializers should not introduce a new dimension of unsafety. Pointer
type conversion can easily lead to undefined behavior, and is beyond
the normal concerns of `UnsafePointer` users. 

In order to convert between incompatible pointer types, the user
should be forced to cast through `UnsafeRawPointer`. This signifies
that the operation is recasting raw memory into a different type.

The only way to force users to explicitly cast through
`UnsafeRawPointer` is to introduce a conversion function:

```swift
let p = UnsafePointer<T>(...)
UnsafePointer(UnsafeRawPointer(p).toType(U))
```

Now the word "Unsafe" appears twice in the expression. That's correct
because there are two levels of unsafety (lifetime extension + type
adoption). Now it is explicit that we need to acquire a raw pointer
before converting to an incompatible type.

A common case involves converting return values back from `void*` C
functions. With an initializer, many existing conversions in this form:

```swift
let voidptr = c_function()
let typedptr = UnsafePointer<T>(voidp)
```

Would need to be migrated to this form:

```swift
let voidptr = c_function()
let typedptr = UnsafePointer(voidp, to: T.self)
```

This source transformation appears to be inane. It doesn't obviously
convey more information.

In this case, the initializer does not provide any benefit in terms of
brevity, and the 'toType' API makes the reason for the source change
more clear:

```swift
let voidptr = c_function()
let typedptr = UnsafePointer(voidptr.toType(T))
```

### `moveInitialize` should be more elegant

This proposal keeps the existing `moveInitialize` API but moves it
into the `UnsafeMutableRawPointer` type. To be complete, the API
should now return a tuple:

```swift
  func moveInitialize<T>(from: UnsafePointer<T>, count: Int)
    -> (UnsafeMutableRawPointer, UnsafeMutablePointer<T>)
  func moveInitializeBackward<T>(from: UnsafePointer<T>, count: Int)
    -> (UnsafeMutableRawPointer, UnsafeMutablePointer<T>)
```

However, this would make for an extremely awkward interface. Instead, I've chosen to document that this API is invalid if the underlying raw memory is ever cast to unrelated types.

The `move()` and `moveAssignFrom` methods have a simlar problem.

### String initialization

It is not uncommon for parsers to work with UInt8 buffers rather than
CChar. We probably want to make it easy to construct String objects
from these buffers:

```swift
String.init(cString: UnsafePointer<UInt8>)
```

## Alternatives previously considered

### unsafeBitCast workaround

In some cases, developers can safely reinterpret values to achieve the
same effect as type punning:

```swift
let ptrI32 = UnsafeMutablePointer<Int32>(allocatingCapacity: 1)
ptrI32[0] = Int32()
let u = unsafeBitCast(ptrI32[0], to: UInt32.self)
```

Note that all access to the underlying memory is performed with the
same element type. This is perfectly legitimate, but simply isn't a
complete solution. It also does not eliminate the inherent danger in
declaring a typed pointer and expecting it to point to values of a
different type.

### typePunnedMemory property

We considered adding a `typePunnedMemory` property to the existing
`Unsafe[Mutabale]Pointer` API. This would provide a legal way to
access a potentially type punned `Unsafe[Mutabale]Pointer`. However,
it would certainly cause confusion without doing much to reduce
likelihood of programmer error. Furthermore, there are no good use
cases for such a property evident in the standard library.

### Special UnsafeMutablePointer<RawByte> type

The opaque `_RawByte` struct is a technique that allows for
byte-addressable buffers while hiding the dangerous side effects of
type punning (a _RawByte could be loaded but it's value cannot be
directly inspected). `UnsafePointer<_RawByte>` is a clever alternative
to `UnsafeRawPointer`. However, it doesn't do enough to prevent
undefined behavior. The loaded `_RawByte` would naturally be accessed
via `unsafeBitCast`, which would mislead the author into thinking that
they have legally bypassed the type system. In actuality, this API
blatantly violates strict aliasing. It theoretically results in
undefined behavior as it stands, and may actually exhibit undefined
behavior if the user recovers the loaded value.

To solve the safety problem with `UnsafePointer<_RawByte>`, the
compiler could associate special semantics with a `UnsafePointer`
bound to this concrete generic parameter type. Statically enforcing
casting rules would be difficult if not impossible without new
language features. It would also be impossible to distinguish between
typed and untyped pointer APIs. For example,
`UnsafePointer<T>.load<U>` would be a nonsensical vestige.

### UnsafeBytePointer

This first version of this proposal introduced an `UnsafeBytePointer`. `UnsafeRawPointer` better conveys the type's role with respect to
uninitialized memory. The best way to introduce `UnsafeRawPointer` to
users is by showing how it represents uninitialized memory. It is the
result of allocation, input to initialization, and result of
deinitialization.  This helps users understand the relationship
between initializing memory and imbuing it with a type.

Furthermore, we do not intend to allow direct access to the "bytes" via subscript which would be implied by `UnsafeBytePointer`.

### Alternate proposal for `void*` type

Changing the imported type for `void*` will be somewhat disruptive. We
could continue to import `void*` as `UnsafeMutablePointer<Void>` and
`const void*` as `UnsafePointer<Void>`, which will continue to serve
as an "opaque" untyped pointer. Converting to UnsafeRawPointer would
be necesarry to perform pointer arithmetic or to conservatively handle
possible type punning.

This alternative is *much* less disruptive, but we are left with two
forms of untyped pointer, one of which (`UnsafePointer`) the type
system somewhat conflates with typed pointers.

There seems to be general agreement that `UnsafeMutablePointer<Void>`
is fundamentally the wrong way to represent untyped memory.

From a practical perspective, given the current restrictions of the
language, it's not clear how to statically enforce the necessary rules
for casting `UnsafePointer<Void>` once general `UnsafePointer<T>`
conversions are disallowed. The following conversions should be
inferred, and implied for function arguments (ignoring mutability):

- `UnsafePointer<T>` to `UnsafePointer<Void>`

- `UnsafePointer<Void>` to `UnsafeRawPointer`

I did not implement this simpler design because my primary goal was to
enforce legal pointer conversion and rid Swift code of undefined
behavior. I can't do that while allowing `UnsafePointer<Void>`
conversions.

The general consensus now is that as long as we are making source
breaking changes to `UnsafePointer`, we should try to shoot for an
overall better design that helps programmers understand the concepts.
