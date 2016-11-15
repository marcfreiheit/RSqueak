#!/bin/bash
file="__run.st"
cat <<EOF> $file
FileStream stdout nextPutAll: 'BENCHMARKS = ['; cr.
Benchmark allSubclassesDo: [:class |
    ((class category startsWith: 'Benchmark') or: [
      class isAbstract or: [
      class isAbstractClass]]) not ifTrue: [
        class benchmarkSelectors do: [:sel |
		FileStream stdout nextPutAll: '"', class, '.', sel, '",'; cr]]].
FileStream stdout nextPut: $]; cr; flush.
Smalltalk quitPrimitive.
EOF
cog32/squeak Spur32.image $file
rm $file