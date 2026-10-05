Sayrift Android third-party runtime materials

This directory accompanies the Android application. Open THIRD_PARTY_NOTICES.txt
for the collected readable notices and inventory.json for coordinates, artifact
SHA-256 hashes, source URLs, POM license declarations and evidence-file hashes.
The companion sayrift-android-runtime-notices.zip contains identical files.

The inventory is the resolved releaseRuntimeClasspath before R8 shrinking, not
a claim that every input class survives in the APK. Local project :core is
Sayrift's own code. Build/test tools and BOM-only constraints are not runtime
artifacts. No local cache paths or signing details are included.

Each module has its published POM and all distinct copyright/license comments
found in its matching published source archive. Embedded AAR/JAR notices are
preserved separately, including notices inside classes.jar and nested JARs.
Full upstream license texts and notices supplement these materials; a common
Apache-2.0 text alone is not used as evidence for all included content.

Additional materials:
- Kotlin JVM standard library: JetBrains copyright; GWT/Guava Apache notices;
  Boost Software License 1.0 for MathJVM-derived functions. The upstream Kotlin
  license README describes other compiler/platform components too; its inclusion
  preserves source evidence and does not mean the Kotlin compiler is in the APK.
- kotlinx.coroutines and kotlinx.serialization: their versioned upstream NOTICE.
- OkHttp public suffix rule data: Mozilla Public License 2.0 and original embedded
  NOTICE. upstream/public_suffix_list.dat is the complete editable rule data
  losslessly decoded from this resolved JAR's publicsuffixes.gz (including !
  exception rules). The upstream list is https://publicsuffix.org/list/ . No
  current online list is substituted for the actual bundled version.
- graphics-path 1.0.1: native C++ source and CMake evidence from AndroidX release
  commit 8a05a22af450d589ef911d772a001a49dcb05b71; AOSP/Filament math copyright
  headers are retained in full. Its CMake target compiles Conic.cpp,
  PathIterator.cpp and pathway.cpp, with no separately linked Skia library.
  LLVM/Clang 14.0.7 revision 4c603efb0cca074e9238af8b4106c30add4418f6 is recorded
  in all four AAR native libraries. LLVM, compiler-rt, libc++ and libc++abi license
  texts at that revision accompany them, including Apache exceptions and the
  upstream legacy MIT/UIUC notices. These toolchain materials conservatively
  retain notices; they do not assert every toolchain component is linked.

Upstream author names and contact details in unmodified public license/source
materials are retained as attribution. They are not local developer information.
Sayrift's original code retains its own MIT license; third-party materials
retain their respective terms. No upstream endorsement is implied.
