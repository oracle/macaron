# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.

.PHONY: clean

all: libfunctors.so

libfunctors.so: functors.o
	g++ --std=c++17 -shared -o libfunctors.so functors.o

functors.o: functors.cpp
	g++ --std=c++17 functors.cpp -c -fPIC -o functors.o

clean:
	rm -f functors.o libfunctors.so