---
layout: default
title: VoidPointer API for In-Memory Layout
categories: proposal
date: 2016-03-23
---

# VoidPointer API for Explicit Layout

## Introduction

UnsafePointer and UnsafeMutable refer to a typed region of memory, and
the compiler must be able to assume that UnsafePointer pointee type is
consistent with other access to the same memory[1]. Consequently,
UnsafePointer conversion exposes an easy way to abuse the type
system. No alternative currently exists for manual memory layout and
direct access to untyped memory, which leads to an overuse of
UnsafePointer. These uses of UnsafePointer, which depend on pointer
type conversion, make accidental type punning likely, which is
semantically undefined behavior and defacto undefined behavior given
the optimizer's long time treatment of UnsafePointer.

[1]:For more details, see the [UnsafePointer documentation](!!!).

In this document, all mentions of UnsafePointer also apply to
UnsafeMutablePointer.

## Motivation

To avoid accidental type punning, we should prohibit direct conversion
between UnsafePointer<T> and UnsafePointer<U> unless the target of the
conversion is UnsafePointer<Void>. To support this change we should
provide an API for accessing an untyped region of memory. Consider
that an UnsafePointer<Void> or OpaquePointer may be obtained from an
external API. However, the developer may know the memory layout and
may want to read or write elements whose types are compatible with
that layout. If the developer cannot guarantee that all accesses to
the same memory location have the same type, then they cannot use
UnsafePointer to access the memory.

## Proposed solution

Introduce a VoidPointer type and API for loading and storing arbitrary
types at specified byte offsets and obtaining an opaque pointer to
specified byte offsets.

Introducing a separate VoidPointer type would also make it possible to
statically prohibit general UnsafePointer conversion while allowing
UnsafePointer to VoidPointer conversion.

## Detailed design

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

Occasionally, we need to convert from a VoidPointer to an
UnsafePointer. This should only be done in very rare circumstances
when the author understands the compiler's strict type rules for
UnsafePointer. For now, this can be done by going through an
OpaquePointer, but we should add an explicit unsafe pointer cast that
makes the risks more obvious and self-documenting. For example:

extension VoidPointer {
  // Sufficiently scary and informative comment mentioning that
  // UnsafePointer's element type is strict.
  bindElementType() -> UnsafePointer<T>
}

## Impact on existing code

Several stdlib uses of UnsafePointer will be converted to
VoidPointer. Hopefully this will set a precedent for developers to
follow UnsafePointer's strict type rules and use VoidPointer
for manual layout.

Disallowing VoidPointer -> UnsafePointer direct conversion will
require some stdlib code, such as HeapBuffer, to use an explicit API
for conversion, such as 'bindElementType' API mentioned above.

unsafeAddress() will now return a VoidPointer, not an UnsafePointer<Void>.

The stdlib String implementation likes to cast between different views
of the string storage. An expert in this area needs to review the code
to determine whether it follows strict type rules and how to best
legalize the code using the proposed APIs.

## Alternatives considered

We considered adding an typePunnedMemory property to the existing
Unsafe[Mutabale]Pointer API. This would provide a legal way to access
a potentially type punned Unsafe[Mutabale]Pointer. However, it would
certainly cause confusion without doing much to reduce likelihood of
programmer error.

The opaque _RawByte struct is a clever techinique that allows for
byte-addressable buffers while preventing type punning (a _RawByte
could be loaded but it's value cannot be directly
inspected). UnsafePointer<_RawByte> is a compelling alternative to
VoidPointer, but the API is less obvious and more cumbersome without a
distinct nominal type. For example, how would UnsafePointer<T> to
UnsafePointer<_RawByte> conversion be implemented? Another problem is
that the loaded _RawByte could be accessed via unsafeCast, which would
mislead the author into thinking that they have legally
bypassed the type system. However, doing so would be illegal.

In some cases, developers *can* safely reinterpret values to achieve the
same effect as type punning:

```
let iptr = UnsafeMutablePointer<Int>(allocatingCapacity: 1).initialize
#if arch(x86_64)
uptr.pointee = U()
// Load T at this address

Note that all access to the underlying memory is performed with the same element type.
This is perfectly legitimate and should probably be preferred over
dropping to VoidPointer.
