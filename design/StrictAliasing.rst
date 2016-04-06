:orphan:

=====================
Swift Strict Aliasing
=====================

Specification
=============

Swift follows strict aliasing rules. The language generally prevents
violation of these rules; however, code that uses unsafe APIs or
imports types can circumvent the language's natural type
safety. Consider the following example of *type punning* using the
UnsafePointer type::

  let ptrToT = UnsafeMutablePointer<T>(allocatingCapacity: 1)
  // Store T at this address.
  uptr.pointee = T()
  // Load U at this address
  let u = UnsafePointer<U>(ptrToT).pointee

The program exhibits undefined behavior unless 'T' and 'U' are
**related types** [#]_ and the loaded type 'U' is **layout
compatible** with the stored type 'T' [#]_. This applies to any two
accessess to the same memory location within the same Swift
program. All accesses to a location must have a related type, all
loads must be layout compatible with stores to the same address, and
all stores to the same address must be commutatively layout
compatible.

.. [#] **related types**: Two value types are related if: (a) the
      types are identical or aliases of each other; or (b) one type
      may be a tuple, enum, or struct that contains the other type as
      part of its own storage; or (c) one type may be an existential
      that the other type conforms to; or (d) both types are classes
      and one is a superclass of the other.

.. [#] **layout compatible types**: Two types are layout compatible if
       their in-memory representation has the same size and alignment
       and the same number of mutually layout compatible
       elements. Some "obvious" examples of layout compatible types
       are:

  - integers of the same multiple-of-8 size in bits
  - floating point types of the same size
  - class types and AnyObject existentials
  - pointer types (e.g. OpaquePointer, UnsafePointer)
  - thin function, C function, and block function types
  - imported C types that have the same layout in C
  - nonresilient structs with one stored property and their stored property
    type
  - nonresilient enums with one case and their payload type
  - nonresilient enums with one payload case (and zero or more
    no-payload cases) have a layout compatible payload type, but *not*
    commutatively.    
  - homogeneous tuples, fixed-sized array storage of the same element type,
    and homogeneous nonresilient structs in which the element type has no spare bits
    (structs may be bit packed).

Note that many types are layout compatible but not related. For example, Int32 and UInt32 are "obviously" layout compatible

If a loaded value must be converted 


Legally Circumventing Strict Aliasing
=====================================

Reinterpreting a value should be done using unsafeBitCast should generally not be used to reinterpret pointer types. If it is used on pointers then it is subject to the same rules as UnsafePointer conversion for avoiding undefined behavior.

Example

In the future, an API will likely exist to allow legal type punning. Loads and stores of type punned memory would still need to follow the rules for layout compatible loads and stores, but the types would not need to be related.


Exempt Types
============

Swift does not currently specify any types that are exempt from strict
aliasing. In the future, it may be useful to declare certain types as
exempt--for example, that 'UInt8' aliases with all other
types. However, this is not currently true; therefore all accesses to
a memory location must have a related type.
