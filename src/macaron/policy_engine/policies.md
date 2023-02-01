
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

Rules with ungrounded values are not allowed, this includes rules like

```
rule(a, b) :- b = 10. // a is ungrounded
rule(_, b) :- b = 10. // _ wildcard is ungrounded
```

### Negation is not grounding

A negation statement does not ground the name in the enclosing rule, so the
following is also not allowed:

```
rule(a, b) :- b = 10, !another_rule(a).
```

### No cyclic negation

A rule is not allowed to recurse through negation:

```
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

```
.decl rel(c:number, b:number)
rel(b, a) :- a = sum c : {relationname(b,_, c)}. // b is not grounded
```

But the below _does_ work:

```
rel(b, a) :-
    relationname(b,_,_),  // b is grounded
    a = sum c : {relationname(b,_, c)}.
```

### No nested aggregates

Aggregate statements that contain other aggregate statements are not allowed,
for example nested sum.

```
D(s) :- s = sum y : { Prime(n), y = sum z : { Prime(z), z < n }, y < 10 }.
```

### No recursion through aggregates

Relations that recurse through an aggregate are not allowed:

```
.decl rel(c:number, b:number)
rel(b, a) :- a = count : {rel(_,_)}.
```

### ADTs

- [ADTs](https://souffle-lang.github.io/types#algebraic-data-types-adt) cannot
    be stored in SQLite database, they can only be imported/exported as fact
    files.
