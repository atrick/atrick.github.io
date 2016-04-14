:orphan:

=======================
Type Safe Memory Access
=======================

This is work-in-progress, not an official language specification.

.. contents:: :local:
   
Introduction
============

Swift enforces type safe access to memory and follows strict aliasing
rules. However, code that uses unsafe APIs or imported types can
circumvent the language's natural type safety. Consider the following
example of *type punning* using the ``UnsafePointer`` type::

  let ptrT = UnsafeMutablePointer<T>(allocatingCapacity: 1)
  // Store T at this address.
  ptrT[0] = T()
  // Load U at this address
  let u = UnsafePointer<U>(ptrT)[0]

The program exhibits undefined behavior unless ``T`` and ``U`` are
`related types`_ and the loaded type ``U`` is **layout compatible**
with the stored type ``T`` (see `Layout Compatible Types`_).

.. admonition:: NOTE

   ``Unsafe[Mutable]Pointer`` is a type safe API. When a program
   accesses memory via ``UnsafePointer``, The ``UnsafePointer``
   element should be consistent with the type used to allocate the
   memory. The "unsafe" in ``UnsafePointer`` actually refers to memory
   management--it is the user's responsibility to manage the object's
   lifetime. Type safety is not only a desirable programming model, it
   is an absolute requirement performance reasons, and ``UnsafePointer``
   is intended for high-performance implementation of data
   structures.


Related Types
=============

Two types are related if any of these conditions hold:

1. the types may be identical or aliases of each other
2. one type may be a tuple, enum, or struct that contains the other
   type as part of its own storage
3. one type may be an existential such that a conformance may contain
   the other type as part of its own storage
4. both types may be classes and one may be a superclass of the other

See `Related Type Examples`_.

Strict Alias Rules
------------------

1. Class references to the same object must be related.

2. Typed pointers to overlapping memory must be related.

Given any two memory accesses, at least of which is a store, that
exist statically within the same Swift program, if the address
expressions depend on a value that dynamically violates strict
aliasing rules, then the program exhibits undefined behavior.

.. admonition:: NOTE

   A subtle aspect of this is that generation of an address that
   violates strict aliasing is not in itself undefined behavior. The
   address does need to be accessed by the program code, and one of
   those accesses must write to memory. For details, see `Pointer
   Casting Example`_.

Exempt Types
------------

Swift does not currently specify any types that are exempt from strict
aliasing. In the future, it may be useful to declare certain types as
exempt--for example, that ``UInt8`` aliases with all other types. Since
this is not currently the case, all accesses to a memory location must
have a related type.


Layout Compatible Types
=======================

Two types are mutually layout compatible if their in-memory
representation has the same size and alignment or they have the same
number of mutually layout compatible elements. Layout compatibility is
specified as part of the ABI and may be expanded over time, so this
document is not meant to be authoritative or complete. Nonetheless,
some "obvious" cases of mutually layout compatible types are:

  - identical types and type aliases
  - integers of the same multiple-of-8 size in bits
  - floating point types of the same size
  - class types and ``AnyObject`` existentials
  - pointer types (e.g. ``OpaquePointer``, ``UnsafePointer``)
  - thin function, C function, and block function types
  - imported C types that have the same layout in C
  - nonresilient structs with one stored property and their stored
    property type
  - nonresilient enums with one case and their payload type
  - the following are all mutually compatible with each other if they
    have the same number and type of elements: homogeneous tuples,
    fixed-sized array storage, and homogeneous nonresilient structs in
    which the element type has no spare bits (structs may be bit
    packed).

Types are layout compatible, but not mutually so, in the following cases:

- aggregates (tuples, array storage, and structs), are layout
  compatible with larger aggregates of the same kind if their common
  elements are mutually layout compatible.

- an enum payload is layout compatible with its enum type if the enum
  has only one payload case (and zero or more no-payload cases).

Layout compatibility is transitive.

.. admonition:: NOTE

   Unrelated class types have no guaranteed heap layout compatibility
   for except for the memory layout within the object's stored
   properties.

.. admonition:: NOTE

   The `proposed resilience document
   <https://github.com/apple/swift/blob/master/docs/archive/Resilience.rst>`_
   explains the impact of resilience on object layout.

See `Layout Compatible Examples`_

Layout Compatible Rules
-----------------------

The following layout rules apply to dynamic memory accesses that occur
during program execution. In particular, they apply to access that
originates from stored property getter and setters, reading from and
assigning into ``inout`` variables, and reading or assigning subscripts
(including the ``Unsafe[Mutable]Pointer`` ``pointee`` property and
subscripts). Aggregate loads and stores can be considered a sequence of
loads and stores of named or indexed elements.

1. Address formation: Given any two accesses to the same memory
   object, the relationship between their address expressions must be
   determined by Swift's ABI for type layout. The addresses may be
   either disjoint or overlapping. If they overlap the offset must be
   determined to be either a named or indexed subobject or known byte
   offset relative to the other. In other words, the access path of
   each load and store must be comparable given layout compatibility
   guarantees. In the case of inout arguments, for the purpose of this
   rule, the address expressions include both generation of the
   argument (caller side) and its use (callee side).

Additionally, the type of the memory access itself must be compatible
with the element type as follows:

2. Loads must be layout compatible with all stores to the same memory object.
3. Stores to the same memory object must be mutually layout compatible.

If the object's allocated type is visible to the Swift program, then
the rules are extended to that allocated type:

4. Loads must be layout compatible with the memory object's allocated type.
5. Stores must be mutually layout compatible with the memory object's allocated type.

Legally Circumventing Strict Aliasing
=====================================

Accessing unrelated layout compatible types requires special
consideration. For example, ``Int32`` and ``UInt32`` are "obviously" layout
compatible; however, simply storing to a location via
``UnsafeMutablePointer<Int32>`` and loading from the same location as
``UnsafePointer<UInt32>`` is undefined.

Reinterpreting a value's bits should be done using ``unsafeBitCast`` to
avoid type punning. For example, the above conversion can be performed
legally as::

  let ptrI32 = UnsafeMutablePointer<Int32>(allocatingCapacity: 1)
  ptrI32[0] = Int32()
  let u = unsafeBitCast(ptrI32[0], to: UInt32.self)

In the future, an API will likely exist to allow legal type
punning. This could be useful for external APIs that require pointer
arguments and for manual memory layout. Loads and stores of type
punned memory would still need to follow the `Layout Compatible Rules`_
for loads and stores, but would be exempt from the `Strict Alias
Rules`_. Such an API, for example, would allow accessing same address
as both ``Int32`` and ``UInt32``.

.. FIXME Reference voidpointer.md once it is a proposal.

Casting Pointers
================

.. FIXME Reference this from SIL.rst, Class TBAA

``unsafeBitCast`` should generally be avoided on pointer types, and should
almost exclusively be avoided on class types. ``unsafeBitCast`` is valid
for pointer to integer conversions. It is also used internally to
convert between nondereferenceable pointer types, which avoids the
need to add builtin conversions for all combinations of pointer
types. As with any conversion to and from opaque pointers, this
presents an opportunity for type punning, so must be used with extreme
caution to avoid undefined behavior.

``unsafeBitCast`` is even more problematic for class types. First, layout
needs to be considered when ``Optional`` or existential class types are
involved. Note that the internal ``_unsafeReferenceCast`` API is preferred
in those cases, because it always handles conversions to and from
optionals and existentials correctly.

Furthermore, ``unsafeBitCast`` of class types may introduce undefined
behavior at the point of access. Normal class casts and class
existential casts rely on the dynamic type to be a subclass of or
conform to the static type at the point of the cast. However, an
``unsafeBitCast`` will succeed when the static and dynamic types are
unrelated, which leads to undefined behavior if the cast pointer
is ever dereferenced. Consider this example::

  class A {
    var i: Int = 3
  }
  class B {
    var i: Int = 3
  }
  
  let a = A()
  let b = unsafeBitCast(a, to: B.self)
  a.i = 10
  print(b.i)

This program exhibits undefined behavior for two reasons. First, it
violates `Strict Alias Rules`_ (#1) because the same memory object may
be accessed via unrelated class types. Second, it violates `Layout
Compatible Rules`_ (#1) because there is no guarantee of layout among
unrelated classes even if they are nonresilient.

Pointer Casting Example
-----------------------

Merely forming an address that violates strict aliasing is not itself
undefined behavior; the address must have some static use within the
code. However, undefined behavior may occur even if those accesses are
themselves never executed. In other words undefined behavior is caused
by a dynamic address and its static uses. For example the following
program is undefined::

  public protocol SomeClass : class {
    func getVal() -> Int
  }
  class ActualClass {
    var i: Int
    init(i: Int) { self.i = i }
  }

  // If 'isActualClass' is true, then 'obj' is a subclass of ActualClass
  // that conforms to SomeClass.
  public func foo<T : SomeClass>(obj: T, isActualClass: Bool) -> Int {
    // This unsafe cast violates the type system because
    // it's operating on class types.
    let actualRef = unsafeBitCast(obj, to: ActualClass.self)
    if (isActualClass) {
      // The unsafe cast is only valid under this condition.
      // Even though this access is never executed when the cast is invalid,
      // it still causes undefined behavior.
      return actualRef.i
    }
    return obj.getVal()
  }

The following code is both legal and more explicit::

  public func foo<T : SomeClass>(obj: T, isActualClass: Bool) -> Int {
    if (isActualClass) {
      // Now we know that the unsafeReferenceCast is type safe.
      let actualRef = unsafeReferenceCast(obj, to: ActualClass.self)
      return actualRef.i
    }
    return obj.getVal()
  }

Examples
========

Related Type Examples
---------------------

Calls to ``related`` and ``unrelated`` obey the `Strict Alias Rules`_::
   
  protocol P {
    var i: Int { get }
  }
   
  protocol Q : class {}
   
  struct S : P {
    var i: Int
  }
   
  enum E {
    case Payload(Int)
  }
   
  class B {
    var i: Int = 3
  }
   
  class C : B {}
   
  class D : P {
    var i: Int = 11
  }
   
  func related(x: inout Int, _ y: inout Int) {}
  func related(x: inout Int, _ y: inout E) {}
  func unrelated(x: inout Int, _ y: inout B) {}
  func unrelated(x: inout Int, _ y: inout Q) {}
   
  func related(x: inout Int, _ y: inout P) {}
  func related(x: inout S, _ y: inout P) {}
  func related(x: inout D, _ y: inout P) {}
  func related(x: inout E, _ y: inout P) {}
  func related(x: inout C, _ y: inout P) {}
   
  func related(x: inout B, _ y: inout C) {}
  func unrelated(x: inout D, _ y: inout C) {}
   
  func access(
    v: inout Int, t: inout (Int, Int), s: inout S, e: inout E,
    p: inout P, q: inout Q, b: inout B, c: inout C, d: inout D) {
   
    // subobject relations
    related(&v, &t.0)
    related(&v, &t.1)
    related(&v, &s.i)
    related(&v, &e)
    related(&v, &c.i)
   
    unrelated(&v, &b) // Classes do not have subobjects.
    unrelated(&v, &q) // Class protocol cannot contain a subobject.
   
    // existential
    related(&v, &p)
    related(&s, &p)
    related(&d, &p)
    related(&e, &p) // An unknown conformance may contain E.
    related(&c, &p) // An unknown conformance may contain a reference to C.
   
    // classes
    related(&b, &c) // subclass relation
   
    unrelated(&d, &c) // no subclass relation
  }

Layout Compatible Examples
--------------------------

Calls to ``mcompatible``, ``compatible``, and ``incompatible`` reflect
`Layout Compatible Rules`_ as their names signify. Calls to ``unknown``
take invalidly formed addresses::
 
  class C {
    var i: Int32 = 7
  }
   
  class D {
    var i: Int32 = 11
  }
   
  struct S1 {
    var i: Int32
  }
   
  struct S2 {
    var i: Int32
    var j: Int32
  }
   
  struct S3 {
    var i: Int32
    var j: Int32
    var k: Int32
  }
   
  struct S2_1 {
    var s2: S2
    var i: Int32
  }
   
  enum E1 {
    case Payload(Int32)
  }
   
  enum E2 {
    case Payload(Int32)
    case NoPayload
  }
   
  struct S_IE2 {
    var i: Int32
    var e2: E2
  }
   
  struct S_SIE2_E2 {
    var sie2: S_IE2
    var e2: E2
  }
   
  struct S_I_E2_E2 {
    var i: Int32
    var e2a: E2
    var e2b: E2
  }

  // Signify mutually compatible access.
  func mcompatible(x: inout Int32, _ y: inout UInt32) {}
  func mcompatible(x: inout C, _ y: inout AnyObject) {}
  func mcompatible<T>(x: inout UnsafePointer<T>, _ y: inout OpaquePointer) {}
  func mcompatible(x: inout Int32, _ y: inout S1) {}
  func mcompatible(x: inout Int32, _ y: inout E1) {}
  func mcompatible(x: inout (Int32, Int32), _ y: inout S2) {}
  func mcompatible(x: inout S2_1, _ y: inout S3) {}

  // Signify one-way layout compatibility.
  func compatible(x: inout Int32, with y: inout E2) {}
  func compatible(x: inout S1, with y: inout S2) {}
   
  func incompatible(x: inout S_SIE2_E2, _ y: inout S_I_E2_E2) {}
   
  func unknown(x: inout Int32, _ y: inout Int32) {}
   
  func access<T>(i: inout Int32, j: inout UInt32, t: inout (Int32, Int32),
    c: inout C, a: inout AnyObject,
    u: inout UnsafePointer<T>, p: inout OpaquePointer,
    s1: inout S1, s2: inout S2, s3: inout S3, s2_1: inout S2_1,
    s_sie2_e2: inout S_SIE2_E2, s_i_e2_e2: inout S_I_E2_E2,
    e1: inout E1, e2: inout E2) {
   
    // mutually compatible
    mcompatible(&i, &j)  // same size integers
    mcompatible(&c, &a)  // class and any object existential
    mcompatible(&u, &p)  // pointers
    mcompatible(&i, &s1) // single element struct
    mcompatible(&i, &e1) // single case enum
    mcompatible(&t, &s2) // tuple and homogeneous struct
   
    // struct { {I32, I32}, I32} vs. struct {I32, I32, I32}; fixed size, no spare bits
    mcompatible(&s2_1, &s3)
    
    // struct { {A, B}, C} vs. struct {A, B, C}; unknown size
    incompatible(&s_sie2_e2, &s_i_e2_e2)
   
    // Compatible: can load one type from an object 'with' another type.
    compatible(&i, with: &e2)  // load the payload from a single payload enum
    compatible(&s1, with: &s2) // load struct {A} from struct {A, B}
   
    // Layout compatibility places no guarantees on class layout. The
    // following unknown call takes two addresses of compatible type
    // (Int32), but the addresses are generated from incompatible class
    // types. Even though the class definitions of 'C' and 'D' are
    // trivial, there is no guarantee that the two addresses passed to
    // this call are identical.
    unknown(&c.i, &unsafeBitCast(c, to: D.self).i)
   
    // Properties within heap storage follow the usual layout rules.
    func getStructPointer(iptr: UnsafeMutablePointer<Int32>)
    -> UnsafeMutablePointer<S1> {
      // Convert from UnsafeMutablePointer<Int32> to UnsafeMutablePointer<S1>
      // with a hypothetical 'unsafeCastElement' label to be explicit.
      return UnsafeMutablePointer(unsafeCastElement: iptr)
    }
    mcompatible(&c.i, &getStructPointer(&c.i).pointee)
  }
