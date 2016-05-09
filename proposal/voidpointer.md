---
layout: default
title:  UnsafeBytePointer API for In-Memory Layout
categories: proposal
date: 2016-05-08
---
# UnsafeBytePointer API for In-Memory Layout

* Proposal: [SE-NNNN](https://github.com/atrick/swift-evolution/blob/voidpointer/proposals/XXXX-unsafebytepointer.md)
* Author(s): [Andrew Trick](https://github.com/atrick)
* Status: **[Awaiting review](#rationale)**
* Review manager: TBD

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
the target of the conversion is an untyped or nondereferenceable pointer
(currently represented as `UnsafePointer<Void>`).

To support this change we should introduce a new pointer type that
does not bind the type of its `Pointee`. Such a new pointer type
would provide an ideal foundation for an API that allows byte-wise
pointer arithmetic and a legal, well-defined means to access an
untyped region of memory.

As motivation for such an API, consider that an `UnsafePointer<Void>` or
`OpaquePointer` may be currently be obtained from an external
API. However, the developer may know the memory layout and may want to
read or write elements whose types are compatible with that
layout. This a reasonable use case, but unless the developer can
guarantee that all accesses to the same memory location have the same
type, then they cannot use `UnsafePointer` to access the memory
without risking undefined behavior.

An `UnsafeBytePointer` example, using a new proposed API is included below.

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

In this proposal, UnsafeBytePointer does not specify
mutability. Adding an UnsafeMutableBytePointer would be
straightforward, but adding another pointer type needs strong
justification. I expect to get input from the community on this. If we
agree that the imported type for `const void*` should be
UnsafeBytePointer, then we probably need UnsafeMutablePointer to
handle interoperability.

## Detailed design

The public API is shown here. For details and comments, see the
[unsafeptr_convert branch][2].

[2]:https://github.com/atrick/swift/commits/unsafeptr_convert

```swift
struct UnsafeBytePointer : Hashable, _Pointer {

  let _rawValue: Builtin.RawPointer

  var hashValue: Int {...}

  init<T>(_ : UnsafePointer<T>)
  init<T>(_ : UnsafeMutablePointer<T>)
  init?<T>(_ : UnsafePointer<T>?)
  init?<T>(_ : UnsafeMutablePointer<T>?)

  init<T>(_ : OpaquePointer<T>)
  init?<T>(_ : OpaquePointer<T>?)

  init?(bitPattern: Int)
  init?(bitPattern: UInt)

  func load<T>(_ : T.Type) -> T

  @warn_unused_result
  init(allocatingBytes size: Int, alignedTo: Int)

  @warn_unused_result
  init<T>(allocatingCapacity count: Int, of: T.Type)

  func deallocateBytes(_ size: Int, alignedTo: Int)

  func deallocateCapacity<T>(_ num: Int, of: T.Type)

  // Returns a pointer one byte after the initialized memory.
  func initialize<T>(with newValue: T, count: Int = 1) -> UnsafeBytePointer

  // Returns a pointer one byte after the initialized memory.
  func initialize<T>(from: UnsafePointer<T>, count: Int) -> UnsafeBytePointer

  func initializeBackward<T>(from source: UnsafePointer<T>, count: Int)

  func deinitialize<T>(_ : T.Type, count: Int = 1)
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
`OpaquePointer`, an explicit, designated unsafe pointer cast API would
makes the risks more obvious and self-documenting. For example:

```swift
extension UnsafePointer {
  init(_ from: UnsafeBytePointer, toPointee: Pointee.type)
}
extension UnsafeMutablePointer {
  init(_ from: UnsafeBytePointer, toPointee: Pointee.type)
}
```

Similarly, conversion between `UnsafePointer` types must now be spelled
with an explicitly `Pointee` type:

```swift
extension UnsafePointer {
  init<U>(_ from: UnsafePointer<U>, toPointee: Pointee.Type)
  init<U>(_ from: UnsafeMutablePointer<U>, toPointee: Pointee.Type)
}
extension UnsafeMutablePointer {
  init<U>(_ from: UnsafeMutablePointer<U>, toPointee: Pointee.Type)
}
```

## Impact on existing code

The largest impact of this change is that `void*` and `const void*`
are imported as UnsafeBytePointer. This impacts many public APIs, but
with implicit argument conversion should not affect typical uses of
those APIs.

Any Swift projects that rely on type inference to convert between
`UnsafePointer` types will need to take action. The developer needs to
determine whether type punning is necessary. If so, they must migrate
to the `UnsafeBytePointer` API. Otherwise, they can work around the
new restriction by using a `toPointee`, or `mutating` label.

Disallowing inferred `UnsafePointer` direct conversion requires some
standard library code to use an explicit `toPointee` label for unsafe
conversions that may violate strict aliasing.

All occurrences of `Unsafe[Mutable]Pointer<Void>` in the standard
library are converted to `UnsafeBytePointer`. e.g. `unsafeAddress()` now
returns `UnsafeBytePointer`, not `UnsafePointer<Void>`.

Some occurrences of `Unsafe[Mutable]Pointer<Pointee>` in the standard
library are replaced with `UnsafeBytePointer`, either because the code was
playing too loosely with strict aliasing rules, or because the code
actually wanted to perform pointer arithmetic on byte-addresses.

`StringCore.baseAddress` changes from `OpaquePointer` to `UnsafeBytePointer`
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
be labeled with `toPointee`.

`CoreAudio` utilities now use an UnsafeBytePointer.


## Implementation status

On my [unsafeptr_convert branch][2], I've made most of the necessary changes to
support the addition of `UnsafeBytePointer` and the removal of inferred
`UnsafePointer` conversion.

There are a several things going on here in order to make it possible
to build the standard library with the changes:

- A new `UnsafeBytePointer` type is defined.

- The type system imports `void*` as UnsafeBytePointer.

- The type system handles implicit conversions to UnsafeBytePointer.

- `UnsafeBytePointer` replaces both `UnsafePointer<Void>` and
  `UnsafeMutablePointer<Void>`.

- The standard library was relying on inferred UnsafePointer
  conversion in over 100 places. Most of these conversions now either
  take an explicit label, such as 'toPointee', 'mutating'. Some have
  been rewritten.

- Several places in the standard library that were playing loosely
  with strict aliasing or doing bytewise pointer arithmetic now use
  UnsafeBytePointer instead.

- Explicit labeled `Unsafe[Mutable]Pointer` initializers are added.

- The inferred `Unsafe[Mutable]Pointer` conversion is removed.


TODO:

Once this proposal is accepted, and the rules for casting between
pointers types have been decided, we need to finish implementing the
type system support. The current implementation (intentionally) breaks
a few tests in pointer_conversion.swift. We also need to ensure that
interoperability requirements are met. Currently, many argument casts
to be explicitly labeled. The current implementation also makes it
easy for users to hit an "ambiguous use of 'init'" error when relying
on implicit argument conversion.

Additionally:

- A name mangled abbreviation needs to be created for UnsafeBytePointer.

- The StringAPI tests should probably be rewritten with
  `UnsafeBytePointer`.

- The NSStringAPI utilities and tests may need to be ported to
  `UnsafeBytePointer`

- The CoreAudio utilities and tests may need to be ported to
  `UnsafeBytePointer`.

## Alternatives considered

### Existing workaround

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

### Discarded alternatives

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
to `UnsafeBytePointer`. However, it doesn't do enough to prevent
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

### Alternate proposal for `void*` type

Changing the imported type for `void*` will be somewhat
disruptive. Furthermore, this proposal currently drops the distinction
between `void*` and `const void*`--an obvious loss of API information.

We could continue to import `void*` as `UnsafeMutablePointer<Void>`
and `const void*` as `UnsafePointer<Void>`, which will continue to
serve as an "opaque" untyped pointer. Converting to UnsafeBytePointer
would be necesarry to perform pointer arithmetic or to conservatively
handle possible type punning.

This alternative is *much* less disruptive, but we are left with two
forms of untyped pointer, one of which (`UnsafePointer`) the type
system somewhat conflates with typed pointers.

Given the current restrictions of the language, it's not clear how to
statically enforce the necessary rules for casting
`UnsafePointer<Void>` once general `UnsafePointer<T>` conversions are
disallowed. The following conversions should be inferred, and implied
for function arguments (ignoring mutability):

- `UnsafePointer<T>` to `UnsafePointer<Void>`

- `UnsafePointer<Void>` to `UnsafeBytePointer`

I did not implement this simpler design because my primary goal was to
enforce legal pointer conversion and rid Swift code of undefined
behavior. I can't do that while allowing UnsafePointer<Void>
conversions.

## API improvements

As proposed, the `initialize` API infers the stored value:

```swift
func initialize<T>(with newValue: T, count: Int = 1) -> UnsafeBytePointer
```

This is somewhat dangerous because the developer may not realize the
size of the object(s) that will be written to memory. This can be
easily asserted by checking the return pointer:

```swift
let newptr = ptr.initialize(with: 3)
assert(newptr - ptr == 8)
```

As an alternative, we could force the user to provide the expected type
name in the `initialize` invocation:

```swift
func initialize<T>(_ T.Type, with newValue: T, count: Int = 1)
  -> UnsafeBytePointer
```

## Future improvements

`UnsafeBytePointer` should eventually support unaligned memory access. I
believe that we will eventually have a modifier that allows "packed"
struct members. At that time we may also want to add a "packed" flag to
`UnsafeBytePointer`'s `load` and `initialize` methods.

When accessing a memory buffer, it is generally convenient to cast to
a type with known layout and compute offsets relative to the type's
size. This is how `UnsafePointer<Pointee>` works. A generic
`UnsafeTypePunnedPointer<Pointee>` could be introduced with the same
interface as `UnsafePointer<Pointer>`, but without the strict aliasing
requirements. This seems like an overdesign simply to avoid calling
`strideof()` in an rare use case, but nothing prevents adding this type later.


## UnsafeBytePointer example

```swift
/// An example of using UnsafeBytePointer to implement manual memory layout.

/// A Buffer for reading and writing basic types at a fixed address.
/// Indirection allows the buffer to refer to mutable state elsewhere.
struct MessageBuffer {
  let ptr: UnsafeBytePointer

  enum IndirectFlag { case Direct, Indirect }

  private func getPointer(atOffset n: Int, _ isIndirect: IndirectFlag)
  -> UnsafeBytePointer {
    switch isIndirect {
    case .Indirect:
      return (ptr + n).load(UnsafeBytePointer.self)
    case .Direct:
      return ptr + n
    }
  }

  func readUInt32(atOffset n: Int, _ isIndirect: IndirectFlag) -> UInt32 {
    return getPointer(atOffset: n, isIndirect).load(UInt32.self)
  }
  func readFloat32(atOffset n: Int, _ isIndirect: IndirectFlag) -> Float32 {
    return getPointer(atOffset: n, isIndirect).load(Float32.self)
  }

  func writeUInt32(_ val: UInt32, atOffset n: Int) {
    getPointer(atOffset: n, .Direct).initialize(with: val)
  }
  func writeFloat32(_ val: Float32, atOffset n: Int) {
    getPointer(atOffset: n, .Direct).initialize(with: val)
  }
  func writeIndirect(_ ptr: UnsafeBytePointer, atOffset n: Int) {
    getPointer(atOffset: n, .Direct).initialize(with: ptr)
  }
}

/// Encoded message format.
struct MessageFormat : Sequence, IteratorProtocol {
  typealias Element = MessageFormat

  private static let maxFormatFields = 32 / 4
  static let maxBufferBytes = maxFormatFields * strideof(UInt)

  var formatCode: UInt32 = 0
  var elementCode: UInt32 = 0
  var offset: Int = 0

  init(bitPattern: UInt32) {
    formatCode = bitPattern
  }

  enum Kind {
    case None, Reserved, UInt32, Float32, IndirectUInt32, IndirectFloat32
  }

  /// The first field's kind.
  var kind : Kind {
    get {
      switch elementCode {
      case 0x0: return Kind.None
      case 0x2: return Kind.UInt32
      case 0x3: return Kind.Float32
      case 0x6: return Kind.IndirectUInt32
      case 0x7: return Kind.IndirectFloat32
      default:  return Kind.Reserved
      }
    }
  }

  func elementStride() -> Int {
    return (elementCode & 0x4) != 0 ? strideof(UInt) : 4
  }

  /// Get the format for the next element.
  mutating func next() -> Element? {
    if elementCode != 0 {
      offset += elementStride()
    }
    elementCode = formatCode & 0xF
    formatCode >>= 4
    if kind == .None {
      return nil
    }
    // align to the next element size
    let offsetMask = elementStride() - 1
    offset = (offset + offsetMask) & ~offsetMask
    return self
  }
}

func createBuffer() -> MessageBuffer {
  return MessageBuffer(ptr: UnsafeBytePointer(
      allocatingBytes: MessageFormat.maxBufferBytes, alignedTo: strideof(UInt)))
}

func destroy(buffer: MessageBuffer) {
  buffer.ptr.deallocateBytes(MessageFormat.maxBufferBytes,
    alignedTo: strideof(UInt))
}

var sharedInt: UInt32 = 42
var sharedFloat: Float32 = 16.25

func generateMessage(inBuffer mb: MessageBuffer) -> MessageFormat {
  let mf = MessageFormat(bitPattern: 0x06727632)
  for field in mf {
    switch field.kind {
    case .UInt32:
      mb.writeUInt32(66, atOffset: field.offset)
    case .Float32:
      mb.writeFloat32(41.625, atOffset: field.offset)
    case .IndirectUInt32:
      mb.writeIndirect(&sharedInt, atOffset: field.offset)
    case .IndirectFloat32:
      mb.writeIndirect(&sharedFloat, atOffset: field.offset)
    case .None:
      fallthrough
    case .Reserved:
      return MessageFormat(bitPattern: 0)
    }
  }
  return mf
}

func handleMessage(buffer mb: MessageBuffer, format: MessageFormat) -> Bool {
  for field in format {
    switch field.kind {
    case .UInt32:
      print(mb.readUInt32(atOffset: field.offset, .Direct))
    case .Float32:
      print(mb.readFloat32(atOffset: field.offset, .Direct))
    case .IndirectUInt32:
      print(mb.readUInt32(atOffset: field.offset, .Indirect))
    case .IndirectFloat32:
      print(mb.readFloat32(atOffset: field.offset, .Indirect))
    case .None:
      fallthrough
    case .Reserved:
      return false
    }
  }
  return true
}

func runProgram() {
  let mb = createBuffer()
  let mf = generateMessage(inBuffer: mb)
  if handleMessage(buffer: mb, format: mf) {
    print("Done")
  }
  destroy(buffer: mb)
}
runProgram()
```