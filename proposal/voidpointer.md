---
layout: default
title: VoidPointer API for In-Memory Layout
categories: proposal
date: 2016-03-23
---

# VoidPointer API for Explicit Layout

## Introduction

`UnsafePointer` and `UnsafeMutable` refer to a typed region of memory,
and the compiler must be able to assume that `UnsafePointer` element
(`pointee`) type is consistent with other access to the same
memory. See [proposed Type Safe Memory Access
documentation][1]. Consequently, infered conversion between
UnsafePointer element types exposes an easy way to abuse the type
system. No alternative currently exists for manual memory layout and
direct access to untyped memory, and that leads to an overuse of
UnsafePointer. These uses of UnsafePointer, which depend on pointer
type conversion, make accidental type punning likely, which is
semantically undefined behavior and defacto undefined behavior given
the optimizer's long time treatment of UnsafePointer.

[1]:https://github.com/atrick/swift/blob/type-safe-mem-docs/docs/TypeSafeMemory.rst

In this document, all mentions of UnsafePointer also apply to
UnsafeMutablePointer.

## Motivation

To avoid accidental type punning, we should prohibit direct conversion
between `UnsafePointer<T>` and `UnsafePointer<U>` unless the target of the
conversion is `UnsafePointer<Void>`. To support this change we should
provide an API for accessing an untyped region of memory.

Consider that an `UnsafePointer<Void>` or `OpaquePointer` may be obtained
from an external API. However, the developer may know the memory
layout and may want to read or write elements whose types are
compatible with that layout. This a reasonble use case; however,
unless the developer can guarantee that all accesses to the same
memory location have the same type, then they cannot use UnsafePointer
to access the memory.

## Proposed solution

Introduce a VoidPointer type and API for loading and storing arbitrary
types at specified byte offsets and obtaining an opaque pointer to
specified byte offsets.

Introducing a separate VoidPointer type also makes it possible to
statically prohibit general UnsafePointer conversion while allowing
UnsafePointer to VoidPointer conversion.

## Detailed design

```swift
struct VoidPointer {
  init(from: OpaquePointer)
  init<T>(from: UnsafePointer<T>)

  init(from: VoidPointer, atOffset: Int)
  load<T>(_: T.Type, atOffset: Int) -> T
  store<T>(value: T, atOffset: Int)
}

extension OpaquePointer {
  init(from: VoidPointer, atOffset: Int)
}
```

Occasionally, we need to convert from a VoidPointer to an
UnsafePointer. This should only be done in very rare circumstances
when the author understands the compiler's strict type rules for
UnsafePointer. Although this could be done by casting through an
OpaquePointer, an explicit unsafe pointer cast would makes the risks
more obvious and self-documenting. For example:

```swift
extension UnsafePointer {
  /// - Warning: the behavior of accesses to pointee as a type
  ///   different from that to which it was initialized is undefined.
  init<U>(unsafeCastPointer from: UnsafePointer<U>) {
     _rawValue = from._rawValue
  }
}
```

## Impact on existing code

Several stdlib uses of UnsafePointer will be converted to
VoidPointer. This will set a good precedent for developers to
follow UnsafePointer's strict type rules and use VoidPointer
for manual layout.

Disallowing VoidPointer to UnsafePointer direct conversion will
require some stdlib code, to use an explicit API for conversion, such
as ``unsafeCastElement`` API mentioned above. These changes can be
seen on the following branch:
https://github.com/atrick/swift/tree/unsafeptr_convert

`unsafeAddress()` will now return `VoidPointer`, not `UnsafePointer<Void>`.

The stdlib String implementation likes to cast between different views
of the string storage. The code generally demonstrates awareness of
strict aliasing rules. However, an expert in this area should review
it to determine whether it always follows strict type rules and how to best
legalize the code using the proposed APIs.

## Implementation Status

On the following branch, I've made most of the necessary changes to
support the addition of VoidPointer and the removal of infered
UnsafePointer conversion:
https://github.com/atrick/swift/tree/unsafeptr_convert

There are a several things going on here in order to make it possible
to build the standard library with the changes:

- A new VoidPointer type is defined. Suggestions for refactoring welcome.

- unsafeAddressOf returns VoidPointer instead of UnsafePointer<Void>.

- The default Unsafe[Mutable]Pointer conversion is removed.

- Many places in the standard library were relying on default
  conversion in potentially type-unsafe situations. These conversions
  now either take a 'mutating' label or an 'unsafeCastElement' label.

- The type system becomes aware of the special VoidPointer type

- The type system handles conversions between VoidPointer and other
  points (attempting to emulate the old behavior of
  UnsafePointer<Void>).

- External APIs still require UnsafeMutablePointer<Void>, so some of
  these arguments are explicitly converted from VoidPointer. I expect
  these to be cleaned up with proper type system support.

I don't want to commit these changes as is because it may break
code that relies on implicit UnsafePointer conversions and imported
types (I've made attempts at fixing this but it's clearly
incomplete). I'd like to get most of the changes in without actually
removing the default UnsafePointer conversion. Then I'd like help from
type system experts for finishing support for implicit conversion and
imported types. Once that's done, actually removing the UnsafePointer
conversion will be as transparent as possible.

## Alternatives considered

We considered adding an typePunnedMemory property to the existing
`Unsafe[Mutabale]Pointer` API. This would provide a legal way to access
a potentially type punned `Unsafe[Mutabale]Pointer`. However, it would
certainly cause confusion without doing much to reduce likelihood of
programmer error.

The opaque `_RawByte` struct is a clever technique that allows for
byte-addressable buffers while hiding the dangerous side effects of
type punning (a _RawByte could be loaded but it's value cannot be
directly inspected). `UnsafePointer<_RawByte>` is a clever alternative
to `VoidPointer`, but the API is less obvious and more cumbersome
without a distinct nominal type. For example, how would
`UnsafePointer<T>` to `UnsafePointer<_RawByte>` conversion be
implemented? Another problem is that the loaded `_RawByte` could be
accessed via `unsafeBitCast`, which would mislead the author into
thinking that they have legally bypassed the type system. In
actuality, this API blatanly violates strict aliasing. It
theoretically results in undefined behavior as it stands, and may
actually exhibit undefined behavior if the user recovers the loaded
value.

In some cases, developers *can* safely reinterpret values to achieve the
same effect as type punning:

```swift
let ptrI32 = UnsafeMutablePointer<Int32>(allocatingCapacity: 1)
ptrI32[0] = Int32()
let u = unsafeBitCast(ptrI32[0], to: UInt32.self)
```

Note that all access to the underlying memory is performed with the
same element type.  This is perfectly legitimate and much preferred
over dropping to VoidPointer.
