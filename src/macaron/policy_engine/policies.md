
# Writing Souffle Policies

Souffle has 3 common types of statement

### Declarations

```
.decl relationname(a: number, b: symbol, c: number)
```

These declare a rule that relates multiple pieces of information.

### Facts


```
relationname(10, "Hello", 0).
```

These declare a piece of information, like a database row.

### Relations

```
relationname (a, b, c + 1) :-  relationname(a, b, c), c < 3.
```

These infer new facts from the existing facts, here the resulting output would be:

```
---------------
relationname
a       b       c
===============
10      Hello   0
10      Hello   1
10      Hello   2
10      Hello   3
===============
```


## Limitations

### Concept: grounding

The souffle datalog program must be monotonic: when evaluated its constraints must converge to a fixed point. This means all
rules have to either make their domain smaller, or make the domain finitely larger. Grounding means there is a finite
bound on the facts derived from the relation.  

For example putting a wildcard on the left hand side of the rule means the derived domain is not restricted to a finite set of
facts, and souffle would run forever trying to enumerate all possible values. Abstractly this set is infinite, so such
a rule is not allowed in the language.

All rules must be grounded so rules like below are not allowed:

```
rule(a, b) :- b = 10. // a is ungrounded
rule(_, b) :- b = 10. // _ wildcard is ungrounded
```

### Negation is not grounding

A negation statement does not ground the name in the enclosing rule, so the
following is also not allowed:


```c
rule(a, b) :- b = 10, !another_rule(a).
```

This is because negation means "everything except `another_rule(a)`", which is an infinite set of facts.

We can fix this by giving the rule an upper bound, or grounding it: the following rule is allowed:

```c
rule(a, b) :- b = 10, a = 10, !another_rule(a).
```

Now the domain of `a` is finite, and the rule can be evaluated to produce a finite number of facts. Of course this
rule has a different meaning before: nowhere in datalog is it allowed to have a rule that produces an unbounded set of
facts.

### No cyclic negation

A rule is not allowed to recurse through negation:

```c
.decl rel(a: symbol)
rel("Hello").
rel("HellWorld") :- !rel("HelloWorld").
```

### The witness problem

Souffle supports [aggregate functions](https://souffle-lang.github.io/aggregates);
max, min, sum, etc. but unless they fix on
a single element of the aggregate (eg. the minimum), they cannot ground
a relation from the inside.

For example you cannot write

```c
.decl rel(c:number, b:number)
rel(b, a) :- a = sum c : {relationname(b,_, c)}. // b is not grounded
```

But the below _does_ work:

```c
rel(b, a) :-
    relationname(b,_,_),  // b is grounded
    a = sum c : {relationname(b,_, c)}.
```

### No nested aggregates

Aggregate statements that contain other aggregate statements are not allowed,
for example nested sum.

```c
D(s) :- s = sum y : { Prime(n), y = sum z : { Prime(z), z < n }, y < 10 }.
```

### No recursion through aggregates

Relations that recurse through an aggregate are not allowed:

```
.decl rel(c:number, b:number)
rel(b, a) :- a = count : {rel(_,_)}.
```

## Alternatives to Aggregates


Example facts:
```c
.decl nums(x:number, y: number)
nums(1,5).
nums(3,2).
nums(4,2).
nums(1,2).
```

---

Datalog assumes all facts that exist are true, and fact that does not exist is false.
So if we have a fact `relation(x,y)` we are also implicitly saying $\exists relation(x,y)$.

### Exists / Any

- Writing `any <relation> <predicate>`, or $\exists\: relation | predicate$
    - write `<relation>, <predicate>`

```c
// there exists nums(x,y), where x = 4
.decl any_x(x:number, y: number)
any_x(x,y) :- nums(x,y), x = 4.
```
output:
```
any_x
x       y
===============
4       2
===============
```

### All

- Specifying `for all <relation>, <predicate>`, $\forall relation | predicate$
    - Write the same thing by saying `not (some <relation> not <predicate>)` or $\not\exists relation | \neg predicate$.
      In datalog this is `<relation>, <negative predicate>`, however it has to be split into multiple relations:

For example to write `for all nums(x,y), y = 2`

```c
// there exists a nums(x,y) where y != 2
.decl any_nx(x:number, y: number)
any_nx(x,y) :- nums(x,y), y != 2.

.decl all_x()

// there does not exist any_nx()
all_x() :- !any_nx(_,_).
.output all_x
.output any_nx
```
Output:
```
any_nx
x       y
===============
1       5
===============
---------------
all_x

===============
===============
```

If we cannot negate the predicate, we could also use an aggregate to check:

```c
.decl all_y()
all_y() :- count : nums(x,2) = count : nums(_,_).
```


### Subsumption rule: Ordering

If you want to define a partial order: for example to find a maximum or minimum.

It has the syntax `atom <= atom2 :- disjunction`. It replaces atom1 with atom2 if disjunction holds. The fact `atom1` is
actually removed.

- `min(x max(y nums))`

```c
min_x(x,y) :- nums(x,y).
min_x(x,y) <= min_x(x2,y) :- x2 <= x.

max_y(x,y) :- min_x(x,y).
max_y(x,y) <= max_y(x,y2) :- y2 >= y.
```
Output:
```
---------------
min_x
x       y
===============
1       2
1       5
===============
---------------
max_y
x       y
===============
1       5
===============
```

## Other Limitations

### ADTs

- [ADTs](https://souffle-lang.github.io/types#algebraic-data-types-adt) cannot
    be stored in SQLite database, they can only be imported/exported as fact
    files.
