---
layout: default
title: Resilient Dispatch
categories: proposal
date: 2017-10-03
---
# Analyzing dispatch performance

When it comes to resilient performance we need to prioritize
future flexibility and ABI simplicity over perceived performance
advantages. Being able to react to future performance issues that
arise with specific apps is far more important than benchmarking. Time
not spent implementing complex ABI mechanisms is time that will be
spent optimizing more critical performance areas.

It's easy to say we should simply measure performance and let the data
decide, but it's dangerous to make long term decisions based on
one-off, poorly designed experiments. We can still reason about the
relative strengths of each dispatch technique, keeping in mind many
dimensions of performance.

The primary "performance" concerns are, in roughly decreasing priority:

a. app binary size

b. library binary size

c. load time

d. runtime dispatch overhead

e. runtime metadata size

These all heavily depend on the workload, linker implementation, build
mode, and future hardware. 

Within runtime dispatch overhead (d), we can reason about these
contributions to overhead roughly in decreasing priority, considering
that some costs can be amortized:

d1. depth of dependent loads.

d2. # external loads

d3. # indirect calls.

d4. # external calls

d5. # internal loads, calls, branches

d6. cost of the non-hoistable portion of dispatch

# Background

Previously we considered these three **approaches**:

1. Expose vtables as ABI.

2. Export per-method dispatch entry points.

3. Export per-class method lookup.

I argued against #1, exposing vtables, because

- It complicates the ABI and reduces flexibility.

- It requires an additional mechanism to compute the vtable base, and
  I strongly disagree with solutions that unconditionally introduce a
  dependent load. (d1++)

- It forces future runtime implementations to explode vtables by
  `num_base_methods * num_subclasses`. (e++)

I argued against #2, per-method dispatch, because

- It exports more symbols. (b++, c++)

- It has no obvious support for super. We still need a some more
  complex dispatch for super calls.

- Amortized performance. Method lookup is not hoistable. (d6++).

# Recent Considerations

We need to reconsider the argument *for* approach #3 now because Jordan
and Slava pointed out that we can't rely on the key feature: constant,
availability-sorted method indices. That means #3 now requires
additional per-method symbols and a dependent external load (d1++). An
alternative floated by Jordan is to use a constant method name hash,
which complicates the ABI and method lookup (d5+++, d6+++).

Taking this into consideration, #2, per-method dispatch, comes out
ahead in my opinion. It has:

- The simplest ABI.

- The simplest implementation (consistent with non-resilient dispatch).

- The smallest app binary size (a--).

- Likely superior performance in all dimensions except library size
  (b++), load time (c++), and non-hoistable runtime overhead (d6++).

Hoistability is a relative non-issue. ABI simplicity, code size, and
the cost of external loads easily outweigh that.

The more interesting performance question is whether introducing
per-method symbols will have a significant impact on library size and
load time. I submit that it is not a serious problem because:

- This only adds one symbol for every publicly declared
  method--inherited methods won't add symbols. That seems within
  normal expectations and no worse than ObjC or C++.

- Symbol stripping, trie-supported symbol table and launch closures
  should mostly mitigate these costs.

Furthermore, a straight-forward implementation of #3, per-class method
lookup, would require the same number of symbols. That could be
avoided by implementing #3 with a hash-based lookup, but that would be
much more complicated and costly in terms of runtime overhead (d6++).

# Super call dispatch

Assuming that #2, per-method dispatch functions have the least
complexity and best performance, that only leaves support for `super`
calls. 

Simply passing a constant flag to distinguish direct vs. dynamic
dispatch is insufficient to handle resilient base classes because
overrides can be added resiliently. Furthermore, at compile time we
don't always statically know the current superclass, since a
superclass override could be injected resiliently:

```
// Module A
public class Base {
  public func foo() { … }
}

public class Sub: Base {
  public override func foo() { … }
}

// Module B
extension Sub {
  func bar() { super.foo() }
}
```

[Jordan's example: If a new superclass is injected between 'Base' and
'Sub', then the extension of 'Sub' in module B should switch to
calling that new class' implementation of 'foo'. We probably also
want to allow the reverse situation: a subclass method overrides a
superclass method without changing the type signature, and at some
point the override no longer becomes necessary, so the implementer
removes it.]

Consequently it's necessary to dynamically load the superclass `isa` 
and either pass that to a lookup helper or to a dispatch method.

## Common SIL Implementation Tasks

Regardless of how we implement super dispatch, we likely need these
SIL extensions:

A SIL instruction to dynamically retrieve a superclass:

`%typePtr = super_metatype $Sub.Type`

A SIL instruction to resolve a class method based on a type
pointer instead of `self`:

`%method = class_metatype_method %typePtr : $Super, #Super.method!1 : $@convention(method)`

## Method Dispatch Calling Convention Hack

It's tempting to hack the existing per-method dispatch functions to
handle `super` dispatch.

The obvious solution is to pass an extra `isa` argument to the method
dispatch function in a way that is mostly ABI compatible with an
internal method call. This would also affect normal method dispatch:

```
// method call from any subclass of `A` to self.foo
%self_isa = value_metatype $A.Type, %self
%foo = function_ref @A.foo : $@convention(external_method) ...
apply %foo(self, args..., %self_isa)

// method call from `B` to super.foo. `super` may be `A` or some
// intermediate subclass.
%super_isa = super_metatype $B.Type
%foo = function_ref @A.foo : $@convention(external_method) ...
apply %foo(self, args..., %super_isa)
```

This approach unnecessarily penalizes normal dispatch in order to
handle the extremely rare case of cross-module super calls:

- It forces an `isa` load on the caller side increasing app size. (a++)

- If forces a thunk to the actual method body along and forces either
  unconditional dynamic dispatch, or an extra `isa` check before doing
  direct dispatch, increasing library size and dispatch cost (b++, d6++)

This also requires implementing a new SIL calling convention so that
`isa` can be passed in a register without shuffling arguments. Note
that even normal method dispatch will now need to access `isa`
immediately on the callee side.

## Method Lookup Implementation

Super class dispatch is naturally implemented with a per-class method
lookup, as in approach #3. We just need an alternative to relying on a
constant method index.

We have already ruled out

- exporting a second per-method symbol

- exporting a method descriptor as the primary per-method symbol,
  which normal dispatch would need to load from.

But, since we have now exported the method dispatch function, that can
serve as an adequate lookup key. The per-class method lookup function
and dispatch function are always associated with the same class
definition. So, the lookup only needs to search for keys directly
defined in its class [see extensions](#extensions). If the method is
not open and there are no known overrides, then the dispatch_function
could be returned without even loading a function pointer.

```
// method call from any subclass of `A` to self.foo
// (this is now an ideal fast path)
%foo = function_ref @A.foo : $@convention(external_method) ...
apply %foo(self, args...)

// method call from `B` to super.foo. `super` may be `A` or some
// intermediate subclass.
%super_isa = super_metatype $B.Type
%A_foo  = function_ref @A.foo : $@convention(external_method) ...
%lookup = function_ref @A.method_lookup : $@convention(external_method) ...
%method = apply %lookup(%super_isa, %A_foo)
%result = apply %method(self, args...)
```

Keep in mind that cross-module super dispatch is expected to be
extremely rare--it's not a critical path and won't have any pervasive
performance impact. It would be quite simple to implement a
linear-time search with immediate comparisons that doesn't require a
lookup table. Typically, the search space will be very small--10 or so
methods. Note that 10 compare-and-branches is typically considered as
fast as an indirect call. Some outliers (e.g. corelibs NSObject) could
have 100s of methods. If this ever becomes a performance problem, then
we can address that without affecting the ABI by:

- Storing a method descriptor in the text segment at a negative offset
  from the dispatch function, with LLVM support.

- Implementing a hash table or some other cached lookup for cases with
  more than X methods.

### Extensions

[John's thought on extensions]

To ensure that we have a lookup function in the correct module and
class for every possible super call, a module will need to export both
a per-class lookup function and a dispatch function whenever it
defines an "ABI-new" public non-final class method. An "ABI-new"
method is either a non-override, was already defined in a previous
version of the library, or is an override that in some way affects the
signature.

# Witness tables

The really sad news, for anyone reading this far, is that this
discussion also applies to protocol methods. We can't rely on
availability of sorted witness tables either. This means that protocol
dispatch will have some resilience overhead--about the same as a
virtual call. Slava suggested exporting a dispatch symbol per method
declared by a Requirement, which is analogous to vtable approach #2.
There is a simplicity advantage to using the same resilience
mechanism for both kinds of dispatch.

The only reasonable alternative I can think of is to continue exposing
witness tables as ABI, but export a symbol for each protocol method
which would store the witness method index. I suspect that the
dependent GOT load will be more expensive than directly calling into a
thunk, but we may want to leave time in the schedule to evaluate this
performance tradeoff before ABI freeze.

I suspect that the best answer here is to allow for @inlinable witness
tables in performance critical cases. However, we don't have a plan
for that in Swift 5. This is a potential performance risk.
