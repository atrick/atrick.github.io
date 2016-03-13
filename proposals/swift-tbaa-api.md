---
layout: page
title: UnsafePointer API for Type Punning
---

# UnsafePointer API for Type Punning

* Proposal: [SE-NNNN](https://github.com/apple/swift-evolution/blob/master/proposals/NNNN-name.md)
* Author(s): [Andrew Trick](https://github.com/atrick)
* Status: **Awaiting review**
* Review manager: TBD

## Introduction

This proposal mainly applies to standard library authors, but does
affect the public UnsafePointer API. The examples use
Builtin.addressof() to directly illustrate key properties of type
based alias analysis. But the same effect can be achieved without a
Builtin via implicit inout argument to UnsafePointer conversion.

Definition: type punning is the act of dereferencing a type punned
pointer. A type punned pointer is one in which multiple aliases of the
same pointer value have unrelated types. There is a subtle
distinction here because type punned pointers are legal, albeit
dangerous, while type punning, if not carefully controlled can lead to
undefined behavior. (You can lie about a type if you don't act on the
lie).

Type based alias analysis is a set of guarantees that allows the Swift
compiler to optimize memory access. Swift follows strict type based
alias analysis rules as described in SIL.rst. These rules are divided
into class TBAA and typed access TBAA.

Class TBAA essentially dictates that a heap objects must be accessed
via a static type that is a superclass of its dynamic type.
Consequently, a single access to a heap object via an incorrect type
is undefined behavior. The following example violates class TBAA:

```swift
class A {
  var i: Int = 0
}
class B {
  var i: Int = 0
}
 
// Accessing a class property via a reference to an unrelated static type
// is undefined.
func foo_class_undef() -> Int {
  var a = A()
  return UnsafePointer<B>(Builtin.addressof(&a)).memory.i
}
```

Typed access TBAA relates to directly dereferencing the address of a
variable or property. The following example shows a typed access to a
type punned Float pointer. This single access, by itself, is well
defined (type punning has not actually occurred because `A.i` is not
accessed as an Int).

```swift
class A {
  var i: Int = 0
}
// Accessing a property of the class using the "wrong" type is perfectly
// fine for alias analysis even though the bit pattern may be nonsense.
func foo_valid(a: A) -> Float {
  var a = a
  return UnsafePointer<Float>(Builtin.addressof(&a.i)).memory
}
```

Now consider an example of type punning that exhibits formal undefined
behavior. In this simple case, the compiler's implementation of
aliasing rules allow the load of the floating point value to occur
before the store `a.i = 42`. In the presense of other code,
interacting compiler optimizations could lead to unanticipated behavior.

```swift
class A {
  var i = 0
}
func foo_pun_undefined(a: A) -> Float {
  var a = a
  a.i = 42
  return UnsafePointer<Float>(Builtin.addressof(&a.i)).memory
}
```

//!!! Swift-evolution thread: [link to the discussion thread for that proposal](https://lists.swift.org/pipermail/swift-evolution)

## Motivation

UnsafePointer is the API that should be used for raw memory access,
and to the unsuspecting user would appear to support type punning, but
doing so results in undefined behavior. The result is a dangerously
misleading API, especially given the lack of alternate functionality.

The Swift standard library should provide an explicit API to perform
type punning when necessary. This is expected to be exceedingly rare
and only for low-level system programming. For example, on some
platforms accessing UnsafePointer<Int> as UnsafePointer<UInt64> may be
desired.

The goal of this proposal is to clarify the rules of the current
UnsafePointer API, and provide an alternate API for type punning that
users can invoke at their own risk. Type punning via
UnsafePointer.memory will continue to be disallowed. This is the
normal, common case, and must be well optimized. The new API will make
it possible to safely type pun but is not meant to encourage the
practice. Rather, it places all the resonsibility on the user by
making sure the compiler does not get in the way.

## Proposed solution

I first propose specifying that type punning is undefined behavior by
commenting the UnsafePointer API.

Next, I propose adding a new property to UnsafePointer that supports
type punning, `punnedMemory`. The broken example from the Introduction
could then be legally rewritten as follows:

```swift
class A {
  var i: Int = 0
}
func foo_punned_valid(a: A) -> Float {
  var a = a
  a.i = 42
  return UnsafePointer<Float>(Builtin.addressof(&a.i)).punnedMemory
}
```

It is the user's responsibility to ensure that all uses of the punned
pointer value follow certain rules. Typically, the user knows that
punning occurs when the UnsafePointer value is created:

```
func foo(pInt: UnsafePointer<Int>) {
  let pUInt64 = UnsafePointer<UInt64>(pInt)
```

However, the unsafe `pUInt64` does not carry any information
indicating that it is a type punned pointer. This is required because
it must remain compatible with normal UnsafePointer APIs. Instead, the
user must ensure that the punned pointer is only passed to code that
either does not access the punned pointer or accesses it only via the
`punnedMemory` API.

For any pair of memory accesses, only one of the accesses must be
marked punned to avoid undefined behavior. This means that it is
possible to perform type punning via pointer to a variable or property
that is accessed elsewhere normally. This is well defined as long as
all normal accesses of the same location (those that do not use
`punnedMemory`) have related types.

Note that the proposed API makes it possible to circumvent typed
access TBAA rules but not class TBAA rules. The following example
still results in undefined behavior:

```swift
class A {
  var i = 0
}
class B {
  var i = 0
}
 
// Accessing a class property via a reference to an unrelated static type
// is *still* undefined.
func foo_class_pun_undefined() -> Int {
  var a = A()
  return UnsafePointer<B>(Builtin.addressof(&a)).punnedMemory.i
}
```

It is not possible to circumvent class TBAA because the compiler has
no ability to reason about aliasing references whose static types are
unrelated in the class hierarchy. If the goal is to type pun a class
property, that must be done by directly acquiring the address of the
property, not the address of the reference to the property's object.

Struct properties, on the other hand, can be accessed through a type
punned address, but are limited by the layout guarantees provided by
the type system. These are out of the scope of this proposal but are
explained in the [resilience
document](https://github.com/apple/swift/blob/master/docs/archive/Resilience.rst).

```swift
struct A {
  var i = 0
}
struct B {
  var i = 0
}
 
// Accessing a struct property via a reference to an unrelated static type
// depends on the layout guarantees provided by the struct definition.
func layout_guaranteed_foo() -> Int {
  var a = A()
  return UnsafePointer<B>(Builtin.addressof(&a)).punnedMemory.i
}
```

## Detailed design

Add a `punned` declaration modifier that only applies to addressors
and commincates type based alias information to the compiler.

Add a new property to UnsafePointer...

```swift

  /// Access the memory at this pointer even though the same memory
  /// location may be accessed elsewhere as an unrelated type.
  public var punnedMemory: Memory {
    @_transparent punned unsafeAddress {
      return self
    }
  }
```

And UnsafeMutablePointer...

```swift
  public var punnedMemory: Memory {
    @_transparent punned unsafeAddress {
      return UnsafePointer(self)
    }
    @_transparent punned nonmutating unsafeMutableAddress {
      return self
    }
  }
```

The type based alias analysis documentation in SIL.rst should be
updated as follows (skip ahead if you don't work on SIL):

1. "Two values of unrelated class types may not alias."

  We need to loosen this restriction to support very few special case stdlib bridged types:

  "Two values of of unrelated class types may not alias if typed
  access on both values (via a ref_element_addr) are visible to the
  SIL program."

  [we do still want to declare undefined behavior even if the typed
  access occurs on disjoint control paths]

2. Alias-introducing operations

  The current description in "Typed Access TBAA" is good in spirit,
  but needs clarity. We should add language like this:

  The optimizer must assume that address typed values may alias unless
  it can determine that a non-alias-introducing operation produces the
  value. The calling convention ensures that address arguments do not
  alias. Conversely, basic block arguments may originate from
  alias-introducing operations.

  [In practice, basic blocks address arguments do not alias, but the
  optimizer is free to create aliasing block arguments. To avoid
  adding a restriction on block arguments, the optimizer will either
  find the finite set of pointer roots or treat the block argument
  conservatively (this will not be a significant issue in practice).]

  Only the following address-producing operations may produce aliasing pointers:

  - pointer_to_address with the "mayalias" flag

    [Note that the aliasing address cannot legitimately escape because
    we cannot load/store addresses and the calling convention
    prohibits aliasing.]

  - unchecked_addr_cast

    [this is the lowest SIL form that Builtin.reinterpretCast can
    take. We can't assume much of anything about it. It should be
    extremely rare in specialized code. Promoting this to a value cast
    makes the aliasing go away.]

  Note that Builtin.inttoptr produces a RawPointer which is not
  interesting because by definition may alias with
  everything. Similarly, Builtin.bitcast and
  Builtin.trunc|sext|zextBitCast cannot produce typed pointers, so
  they are irrelevant for TBAA.

## Impact on existing code

This change has no effect on existing uses of UnsafePointer, which
should not currently be used to achieve type punning.

If the unsafeBitCast API is used anywhere to perform type punning by
casting pointer values, those uses could now be replaces by
UnsafePointer.punnedMemory.

## Alternatives considered

Creating a new UnsafePunnedPointer would complicate the API without
fundamentally solving any safety issues.

The only other alternative would be to require an unsafeBitcast of a
pointer whenever dereferencing a punned pointer. This is a nonsolution
by definition since unsafeBitcast is considered a last resort only
when proper language and library has not yet been
provided. unsafeBitcast also makes more sense for reinterpreting a
value's bits as a different type. In other words, it is meant to be
used on a loaded value, not a pointer addressing the value's
location. Using it for type punning would violate the API's intended
purpose.  Although unsafeBitcast is currently used on pointer values
throughout the standard library, we plan to replace all those uses
with proper support for casting pointers.
