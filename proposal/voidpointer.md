---
layout: default
title: UnsafeBytePointer API for In-Memory Layout
categories: proposal
date: 2016-03-23
---

# UnsafeBytePointer API for In-Memory Layout

## Introduction

`UnsafePointer` and `UnsafeMutable` refer to a typed region of memory,
and the compiler must be able to assume that `UnsafePointer` element
(`Pointee`) type is consistent with other access to the same
memory. See [proposed Type Safe Memory Access
documentation][1]. Consequently, inferred conversion between
`UnsafePointer` element types exposes an easy way to abuse the type
system. No alternative currently exists for manual memory layout and
direct access to untyped memory, and that leads to an overuse of
`UnsafePointer`. These uses of `UnsafePointer`, which depend on pointer
type conversion, make accidental type punning likely. Type punning via
`UnsafePointer` is semantically undefined behavior and de facto undefined
behavior given the optimizer's long-time treatment of `UnsafePointer`.

[1]:https://github.com/atrick/swift/blob/type-safe-mem-docs/docs/TypeSafeMemory.rst

In this document, all mentions of `UnsafePointer` also apply to
`UnsafeMutablePointer`.


## Motivation

To avoid accidental type punning, we should prohibit inferred
conversion between `UnsafePointer<T>` and `UnsafePointer<U>` unless
the target of the conversion is a nondereferenceable pointer (currently
represented as `UnsafePointer<Void>`).

To support this change we should introduce a new pointer type that
does not bind type type of its `Pointee`. Such a new pointer type
would provide an ideal foundation for an API that allows bytewise
pointer arithmetic and a legal, well-defined means to access an
untyped region of memory.

To motivate such an API, consider that an `UnsafePointer<Void>` or
`OpaquePointer` may be currently be obtained from an external
API. However, the developer may know the memory layout and may want to
read or write elements whose types are compatible with that
layout. This a reasonable use case, but unless the developer can
guarantee that all accesses to the same memory location have the same
type, then they cannot use `UnsafePointer` to access the memory
without risking undefined behavior.


## Proposed solution

Introduce an `UnsafeBytePointer` type along with an API for obtaining a
`UnsafeBytePointer` value at a relative byte offset and loading and
storing arbitrary types at that location.

Statically prohibit inferred `UnsafePointer` conversion while allowing
inferred `UnsafePointer` to `UnsafeBytePointer` conversion.

`UnsafeBytePointer` meets multiple requirements:

1. An untyped pointer to memory
2. Pointer arithmetic within byte-addressable memory
3. Type-unsafe access to memory (legal type punning)

`UnsafeBytePointer` will replace `UnsafeMutablePointer<Void>` as the
representation for untyped memory. For API clarify we could consider a
typealias for `VoidPointer`. I don't think a separate
`VoidPointer` type would be useful--there's no danger that
`UnsafeBytePointer` will be casually dereferenced, and don't see the
danger in allowing pointer arithmetic since the only reasonable
interpretation is that of a byte-addressable memory.

Providing an API for type-unsafe memory access would not serve a
purpose without the ability to compute byte offsets. Of course, we
could require users to convert back and forth using bitPatterns, but I
think that would be awkward and only obscure the purpose of the
`UnsafeBytePointer` type.


## Detailed design

```swift
struct UnsafeBytePointer : Hashable, _Pointer {

  let _rawValue: Builtin.RawPointer
  
  init<T>(_ : UnsafePointer<T>)
  init?<T>(_ : UnsafePointer<T>?)

  init<T>(_ : OpaquePointer<T>)
  init?<T>(_ : OpaquePointer<T>?)

  init(bitPattern: Int)
  init(bitPattern: UInt)

  func load<T>(_ : T.Type) -> T

  func initialize<T>(with: T, count: Int) -> UnsafeBytePointer

  func initialize<T>(from: UnsafePointer<T>, count: Int) -> UnsafeBytePointer

  var hashValue: Int
}

extension OpaquePointer {
  init(_ : UnsafeBytePointer)
}

extension Int {
  init(bitPattern: UnsafeBytePointer)
}

extension UInt {
  init(bitPattern: UnsafeBytePointer)
}

extension UnsafeBytePointer : RandomAccessIndex {
  typealias Distance = Int

  func successor() -> UnsafeBytePointer
  func predecessor() -> UnsafeBytePointer
  func distance(to : UnsafeBytePointer) -> Int
  func advanced(by : Int) -> UnsafeBytePointer
}

func == (lhs: UnsafeBytePointer, rhs: UnsafeBytePointer) -> Bool

func < (lhs: UnsafeBytePointer, rhs: UnsafeBytePointer) -> Bool

func + (lhs: UnsafeBytePointer, rhs: Int) -> UnsafeBytePointer

func + (lhs: Int, rhs: UnsafeBytePointer) -> UnsafeBytePointer

func - (lhs: UnsafeBytePointer, rhs: Int) -> UnsafeBytePointer

func - (lhs: UnsafeBytePointer, rhs: UnsafeBytePointer) -> Int

func += (lhs: inout UnsafeBytePointer, rhs: Int)

func -= (lhs: inout UnsafeBytePointer, rhs: Int)

```

Occasionally, we need to convert from a `UnsafeBytePointer` to an
`UnsafePointer`. This should only be done in very rare circumstances
when the author understands the compiler's strict type rules for
`UnsafePointer`. Although this could be done by casting through an
`OpaquePointer`, an explicit unsafe pointer cast would makes the risks
more obvious and self-documenting. For example:

```swift
extension UnsafePointer {
  init(_ from: UnsafeBytePointer, toPointee: Pointee.type) {
    _rawValue = from._rawValue
  }
}
```

Similarly, conversion between `UnsafePointer` types must be spelled
with an explicitly `Pointee` type:

```swift
extension UnsafePointer {
  init<U>(_ from: UnsafePointer<U>, toPointee: Pointee.Type) {
     _rawValue = from._rawValue
  }
}
```

Generic code sometimes performs apparently unsafe conversion of
`UnsafePointer`, but dynamic knowledge of the type actually guarantees
that type punning is impossible. An explicit `dynamicCastPointer`
label will identify these cases:

```swift
extension UnsafePointer {
  /// Convert from any `UnsafePointer`, whose `Pointee` is dynamically
  /// convertable to Self's `Pointee`.
  ///
  /// This is commonly used to generate an UnsafePointer<AnyObject>
  /// from generic containers that are dynamically known to contain
  /// objects.
  init<U>(dynamicCastPointer from: UnsafePointer<U>) {
    _sanityCheck(U.self is Pointee.Type)
    _rawValue = from._rawValue
  }
}
```

We may consider renaming this label to avoid implying that it is a
checked cast (as in C++ dynamic_cast).


## Impact on existing code

All occurrences of `Unsafe[Mutable]Pointer<Void>` in the standard
library are converted to `UnsafeBytePointer`. e.g. `unsafeAddress()` now
returns `UnsafeBytePointer`, not `UnsafePointer<Void>`.

Some other occurrences of `Unsafe[Mutable]Pointer` in the standard
library are replaced with `UnsafeBytePointer`, either because the code was
playing too loosely with strict aliasing rules, or because the code
really wanted to perform pointer arithmetic on byte-addresses.

`StringCore.baseAddress` changes from `OpaquePointer` to `UnsafeBytePointer`
because it is computing byte offsets and accessing the memory
`OpaquePointer` is meant for bridging, but should be truly opaque:
nondereferenceable and not involved in address computation.

Disallowing inferred `UnsafeBytePointer` to `UnsafePointer` direct conversion
requires some standard library code to use an explicit
`unsafeCastPointer` label for unsafe conversion.

The `StringCore` implementation does a considerable amount of casting
between different views of the `String` storage. The current
implementation already demonstrates some awareness of strict aliasing
rules. The rules are generally followed by ensuring that the `StringBuffer`
only be accessed using the appropriate `CodeUnit` within Swift
code. For interoperability and optimization, String buffers frequently
need to be cast to and from `CChar`. This is valid as long access to the
buffer from Swift is guarded by dynamic checks of the encoding
type. These unsafe, but dynamically legal conversion points will now
be labeled with `unsafeCastPointer`. There are still some UTF8/UTF16
conversions that should be auditted by someone more familiar with the
code.

The StringAPI tests should probably be rewritten with `UnsafeBytePointer`.

The NSStringAPI utilties and tests may need to be ported to `UnsafeBytePointer`

The CoreAudio utilities and tests likely need to be ported to
`UnsafeBytePointer`.

Any external Swift projects that rely on type inference to convert
between `UnsafePointer` types will need to take action. The developer
will need to determine whether type punning is necessary. If so, they
will need to migrate to the `UnsafeBytePointer` API. Otherwise, they can
work around the new restriction by using an `unsafeCastPointer` or
`dynamicCastPointer` label.


## Implementation status

On my [unsafeptr_convert branch][2], I've made most of the necessary changes to
support the addition of `UnsafeBytePointer` and the removal of inferred
`UnsafePointer` conversion.

[2]:https://github.com/atrick/swift/tree/unsafeptr_convert

There are a several things going on here in order to make it possible
to build the standard library with the changes:

- A new `UnsafeBytePointer` type is defined. Suggestions for
  refactoring welcome.

- unsafeAddressOf returns `UnsafeBytePointer` instead of `UnsafePointer<Void>`.

- The default `Unsafe[Mutable]Pointer` conversion is removed.

- Many places in the standard library were relying on default
  conversion in potentially type-unsafe situations. These conversions
  now either take a 'mutating' label or an 'unsafeCastElement' label.

- The type system becomes aware of the special `UnsafeBytePointer` type

- The type system handles conversions between `UnsafeBytePointer` and other
  points (attempting to emulate the old behavior of
  `UnsafePointer<Void>`).

- External APIs still require `UnsafeMutablePointer<Void>`, so some of
  these arguments are explicitly converted from `UnsafeBytePointer`. I expect
  these to be cleaned up with proper type system support.

I don't want to commit all of these changes as-is because it may break
code that relies on implicit `UnsafePointer` conversions and imported
types (I've already partially fixed this, but the type system work is
incomplete). My plan is as follows:

1. Get most of these changes into the tree without actually
removing the default `UnsafePointer` conversion.

2. Get assistance from type system experts to finish support for
implicit conversion and imported types.

3. Finally, remove the `UnsafePointer` conversion, which should now be
as transparent as possible.


## Alternatives considered

The obvious downside to introducing a new nominal pointer type is the
duplication of much of `UnsafePointer`'s existing API surface. I believe
this API explosion is fairly limited, and it would always be possible
to implement the `UnsafePointer` API's in terms of the `UnsafeBytePointer` API
wherever performance is not a major concern.

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

We considered adding a `typePunnedMemory` property to the existing
`Unsafe[Mutabale]Pointer` API. This would provide a legal way to
access a potentially type punned `Unsafe[Mutabale]Pointer`. However,
it would certainly cause confusion without doing much to reduce
likelihood of programmer error. Furthermore, there are no good use
cases for such a property evident in the standard library.

The opaque `_RawByte` struct is a technique that allows for
byte-addressable buffers while hiding the dangerous side effects of
type punning (a _RawByte could be loaded but it's value cannot be
directly inspected). `UnsafePointer<_RawByte>` is a clever alternative
to `UnsafeBytePointer`, but the API is less obvious and more cumbersome
without a distinct nominal type. For example, how would
`UnsafePointer<T>` to `UnsafePointer<_RawByte>` conversion be
implemented? Another problem is that the loaded `_RawByte` could be
accessed via `unsafeBitCast`, which would mislead the author into
thinking that they have legally bypassed the type system. In
actuality, this API blatantly violates strict aliasing. It
theoretically results in undefined behavior as it stands, and may
actually exhibit undefined behavior if the user recovers the loaded
value.

Alternatively, the compiler could associate special semantics with a
`UnsafePointer` bound to a concrete generic parameter type, such as
`UnsafePointer<RawByte>`. However, only a distinct nominal type makes it
clear that the type has special semantics and allows static enforcement.

## Future improvements

`UnsafeBytePointer` should eventually support unaligned memory access. I
believe that we will eventually have a modifer that allows "packed"
struct members. At that time we may also want to add a "packed" flag to
`UnsafeBytePointer`'s `load` and `initialize` methods.
