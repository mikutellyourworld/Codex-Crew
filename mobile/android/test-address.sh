#!/bin/sh
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
output="$base/app/build/address-tests"
mkdir -p "$output"
javac -d "$output" "$base/app/src/main/java/dev/codexcrew/mobile/ConnectionAddress.java" "$base/tests/ConnectionAddressTest.java"
java -ea -cp "$output" ConnectionAddressTest
javac -cp "$output" -d "$output" "$base/app/src/main/java/dev/codexcrew/mobile/ConnectionProfiles.java" "$base/tests/ConnectionProfilesTest.java"
java -ea -cp "$output" ConnectionProfilesTest
