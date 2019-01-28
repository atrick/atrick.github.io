---
layout: default
title:  Exclusivity Enforcement in Swift 5
categories: design
date: 2018-01-28
---
# Exclusivity Enforcement in Swift 5

The Swift 5 release enables runtime checking of "Exclusive Access to
Memory" by default in Release builds. Previously, these runtime checks
were only enabled in Debug builds. In this post, I'll explain what
this change means for Swift developers and why it is essential to
Swift's strategy for safety and performance.

# Background

To achieve [Memory
Safety](https://docs.swift.org/swift-book/LanguageGuide/MemorySafety.html),
Swift requires exclusive access to a variable in order to modify that
variable. In essense, a variable cannot be accessed via a different
name for the duration in which the same variable is being modified as
an `inout` argument or as `self` within a `mutating` method.

In the following example, `count` is accessed for modification by
passing it as an `inout` argument. The exclusivity violation occurs
because the `modifier` closure both reads the captured `count`
variable and is called within the scope of the same variable's
modification. Inside the `testCount` function, the variable may only
be safely accessed via the `value` inout argument, and within the
`modified` closure it may only safely be accessed as `$0`.

```
func modifyTwice(_ value: inout Int, by modifier: (inout Int) -> ()) {
  modifier(&value)
  modifier(&value)
}

func testCount() {
  var count = 1
  modifyTwice(&count) { $0 += count }
  print(count)
}
```

As often the case with exclusivity violations, the programmer's
intention is somewhat ambiguous. Do they expect `count` to be printed
as "3" or "4"? Either way, the compiler does not guarantee the
behavior. Worse yet, compiler optimizations can produce subtly
unpredictable behavior in the presence of such errors. To protect
against exclusivity violations and to allow the introduction of
language features that depend on safety guarantees, exclusivity
enforcement was first introduced in Swift 4.0: [SE-0176: Enforce
Exclusive Access to
Memory](https://github.com/apple/swift-evolution/blob/master/proposals/0176-enforce-exclusive-access-to-memory.md).

Compile-time (static) diagnostics catch many common exclusivity
violations, but run-time (dynamic) diagnostics are also required to
catch violations involving escaping closures, properties of class
types, static properties, and global variables. Swift 4.0 provided
both compile-time and run-time enforcement, but run-time enforcement
was only enabled in Debug builds.

In Swift 4.1 and 4.2, compiler diagnostics were gradually strengthened
to catch more and more of the cases in which programmers could skirt
exclusivity rules--most notably by capturing variables in nonescaping
closures or by converting nonescaping closures to escaping
closures. The Swift 4.2 announcement, [Upgrading exclusive access
warning to be an error in Swift
4.2](https://forums.swift.org/t/upgrading-exclusive-access-warning-to-be-an-error-in-swift-4-2/12704),
explains some of the common cases affected by the newly enforced
exclusivity diagnostics.

Swift 5 fixes the remaining holes in the language model and fully enforces
that model<sup>1</sup>. Since run-time exclusivity enforcement is now enabled by
default in Release builds, some Swift programs that previously
appeared well-behaved, but weren't fully tested in Debug mode, could
be affected.

<sup>1</sup>Some rare corner cases involving illegal code aren't yet diagnosed in Release builds, but they will trigger the Debug build assertion: "error: nested function with an implicitly captured inout parameter can only be used as a non-escaping argument”.

# Impact on Swift projects

Exclusivity enforcement in Swift 5 may affect an existing project in two ways:

1. If the project source violates Swift's exclusivity rules (see
   [SE-0176: Enforce Exclusive Access to
   Memory](https://github.com/apple/swift-evolution/blob/master/proposals/0176-enforce-exclusive-access-to-memory.md),
   and Debug testing failed to exercise the invalid code, then
   executing the Release binary could trigger a runtime trap. The
   crash will produce a diagnostic message with the string:

   "Simultaneous accesses to ..., but modification requires exclusive access"

    A source level fix is usually straightforward. The following section shows examples of common violations and fixes.

2. The overhead of the memory access checks could affect the
   performance of the Release binary. While the impact should be small
   in most cases, bugs should be filed for measurable performance
   regressions to help prioritize improvements in this area. As a
   general guideline, avoid performing class property access within
   the most performance critical loops, particularly on different
   objects in each loop iteration. If that isn't possible, it may help
   if the visibility of those class properties is `private` or
   `internal`.

These runtime checks can be disabled via Xcode's "Exclusive Access to
Memory" build setting, which has options for "Run-time Checks in Debug Builds Only" and "Compile-time Enforcement Only":

[<img src="./Xcode Exclusivity Build Settings.png">](Xcode exclusivity build setting)

The corresponding swifc compiler flags are
`-enforce-exclusivity=unchecked` and `-enforce-exclusivity=none`.

While disabling run-time checks may workaround a performance regression, it does not mean that exclusivity violations are safe. Without enforcement enabled, the programmer must take responsibility for following exclusivity rules. Disabling run-time checks in Release builds is strongly discouraged
because, if the program violates exclusivity, then it could exhibit
unpredictable behavior, including crashes or memory corruption. Even if the program appears to function correctly today, future release of Swift could
cause additional unpredictable behavior to surface.

# Examples

The "testCount" example from the Background section violates
exclusivity by passing a local variable as an `inout` argument while
simultaneously capturing it in a closure. The compiler detects this at
build time, as shown in the screen shot below:

[<img src="./Exclusivity Example 1.png">](testCount error)

`inout` argument violations can often be trivially fixed with the
addition of a `let`:

```
let incrementBy = count
modifyTwice(&count) { $0 += incrementBy }
```

The next example may simultaneously modify `self` in a `mutating`
method, producing unexpected behavior. The `append(removingFrom:)`
method appends to an array by removing all the elements from another
array:

```
extension Array {
    mutating func append(removingFrom other: inout Array<Element>) {
        while !other.isEmpty {
            self.append(other.removeFirst())
        }
    }
}
```

However, using this method to append an array to itself will do
something unexpected — loop forever. Here, again the compiler produces
an error at build time because "inout arguments are not allowed to
alias each other":

[<img src="./Exclusivity Example 2.png">](append(removingFrom:) error)

To avoid these simultaneous modifications, the local variable can be
copied into another `var` and passed as ‘inout’ instead:

```
var toAppend = elements
elements.append(removingFrom: &toAppend)
```

The two modifications are now on different variables, so there is no
conflict.

Examples of some common cases that cause build time errors can be
found in [Upgrading exclusive access warning to be an error in Swift
4.2](https://forums.swift.org/t/upgrading-exclusive-access-warning-to-be-an-error-in-swift-4-2/12704).

Changing the first example to use a global rather than local variable
prevents the compiler from raising an error at build time. Instead,
running the program traps with the "Simultaneous access" diagnostic:

[<img src="./Exclusivity Example 3.png">](global count error)

In many cases, as shown in the next example, the conflicting accesses
occur in separate statements.

```
struct Point {
    var x: Int = 0
    var y: Int = 0

    mutating func modifyX(_ body:(inout Int) -> ()) {
        body(&x)
    }
}

var point = Point()

let getY = { return point.y  }

// Copy `y`'s value into `x`.
point.modifyX {
    $0 = getY()
}
```

The runtime diagnostics capture the information that an access started
at the call to `modifyX` and that a conflicting access occured within
the `getY` closure, along with a backtrace showing the path leading to
the conflict:

```
Simultaneous accesses to ..., but modification requires exclusive access.
Previous access (a modification) started at Exclusivity Examples`main + 77 (..).
Current access (a read) started at:
0    swift_beginAccess
1    closure #1
2    Point.modifyX(_:)
Simultaneous accesses to 0x100b95cd0, but modification requires exclusive access.
Previous access (a modification) started at Exclusivity Examples`HasNames.insertAndRecordDuplicate(name:) + 112 (0x100002320).
```

Xcode first pinpoints the inner conflicting access:

[<img src="./Exclusivity Example 4a.png">](Point error: inner position)

Selecting "Previous access" from the current thread's view in the
sidebar pinpoints the outer modification:

[<img src="./Exclusivity Example 4b.png">](Point error: outer position)

The exclusivity violation can be avoided by copying any values that
need to be available within the closure:

```
let y = point.y
point.modifyX {
    $0 = y
}
```

If this had been written without getters and setters:

```
point.x = point.y
```

...then there would be no exclusivity violation, because in a simple
assignment (with no `inout` argument scope), the modification is
instantaneous.

At this point, the reader may wonder why the original example is
considered a violation of exclusivity when two separate properties are
written and read; `point.x` and `point.y`. Because `Point` is declared
as a `struct`, it is considered a value type, meaning that all of its
properties are part of a whole value, and accessing one property
accesses the entire value. The compiler can only make exceptions to
this rule in specific cases in which it can prove safety, such as:

```
func modifyXY(x: inout Int, y: inout Int) { ... }

func testDisjointStructProperties(point: inout Point) {
  modifyXY(x: &point.x, y: &point.y) // Allowed as a special case.
}
```

Properties can be classified into three groups:

1. instance properties of value types

2. instance properties of reference types

3. static and class properties on any kind of type

Only modifications of the first kind of property (instance properties)
require exclusivity access to entire storage of the aggregate value. The
other two kinds of properties are enforced separately, as independent
storage. If this example is converted to a class, the exclusivity
violation goes away:

```
class SharedPoint {
    var x: Int = 0
    var y: Int = 0

    func modifyX(_ body:(inout Int) -> ()) {
        body(&x)
    }
}

var point = SharedPoint()

let getY = { return point.y  } // no longer a violation when called within modifyX

// Copy `y`'s value into `x`.
point.modifyX {
    $0 = getY()
}
```

# Motivation

The combination of compile-time and run-time exclusivity checks
described above are necessary to enforce Swift's [Memory
Safety](https://docs.swift.org/swift-book/LanguageGuide/MemorySafety.html). Fully
enforcing those rules, rather than placing the burden on programmers
to follow the rules, helps in at least five ways:

1. Adherence to exclusivity rules removes a common class of
   programming bugs involving mutable state and action at a distance.

    As programs scale in size, it becomes increasingly likely for
    routines to interact in unexpected ways. Exclusivity rules
    eliminate dangerous interactions involving mutable state. The
    following example is similar in spirit to the
    `Array.append(removingFrom:)` example above, where exclusivity
    enforcement is needed to prevent the programmer from passing the
    same variable as both the source and destination of a move. But
    notice that once classes are involved it becomes much easier for
    programs to unwittingly pass the same instance of `Names` in both
    `src` and `dest` position because two variables reference the same
    object. Again, this causes an infinite loop:

    ```
    func moveElements(from src: inout Set<String>, to dest: inout Set<String>) {
        while let e = src.popFirst() {
            dest.insert(e)
        }
    }
     
    class Names {
        var nameSet: Set<String> = []
    }
     
    func moveNames(from src: Names, to dest: Names) {
        moveElements(from: &src.nameSet, to: &dest.nameSet)
    }
     
    var oldNames = Names()
    var newNames = oldNames // Aliasing naturally happens with reference types.
     
    moveNames(from: oldNames, to: newNames)
    ```

    See [SE-0176: Enforce Exclusive Access to
    Memory](https://github.com/apple/swift-evolution/blob/master/proposals/0176-enforce-exclusive-access-to-memory.md)
    for a more in-depth description of the problem.

2. Enforcement eliminates an unspecified behavior rule from the
   language.

    Prior to Swift 4, these memory safety rules were unenforced,
    making it the programmer's responsibility to adhere to them. Swift
    programmers should not need to understand the intricacies of the
    memory model to write correct code. In practice, it is easy to
    violate these rules in subtle ways, leaving programs susceptible
    to unpredictable behavior, particularly across releases of the
    compiler.

3. Enforcement is necessary for ABI stability.

    Failing to fully enforce exclusivity would have an unpredictable
    impact on ABI stability. Existing binaries built without full
    enforcement may function correctly in one release but behave
    incorrectly in future versions of the compiler, standard library,
    and runtime.

4. Enforcement legalizes performance optimization while protecting
   memory safety.

    A guarantee of exclusivity on `inout` parameters and `mutating`
    methods provides important information to the compiler, which it
    can use to optimize memory access and reference counting
    operations. Declaring an unspecified behavior rule, as mentioned
    above, does not provide this guarantee. An "undefined behavior"
    rule is required to support optimization, but such a rule would,
    by definition, compromise the memory safety of the language. Full
    exclusivity enforcement allows the compiler to optimize based on
    memory exclusivity without introducing undefined behavior.

5. Exclusivity rules are needed to give the programmer control of
   ownership and move-only types.

    The [Ownership
    Manifesto](https://github.com/apple/swift/blob/master/docs/OwnershipManifesto.md)
    intoduces the [Law of
    Exclusivity](https://github.com/apple/swift/blob/master/docs/OwnershipManifesto.md#the-law-of-exclusivity),
    and explains how it provides the basis for adding ownership and
    move-only types to the language.

# Conclusion

By shipping with full exclusivity enforcement enabled in Release
builds, Swift 5 helps to eliminate bugs and security issues, ensure
binary compatibility, and enable future optimizations and language
features.
