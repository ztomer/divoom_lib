#!/bin/bash
set -e

# Helper script to run code coverage metrics for the native Rust daemon.
# Uses `cargo-llvm-cov`.

echo "[ ==> ] Checking cargo-llvm-cov installation..."
if ! command -v cargo-llvm-cov &> /dev/null; then
    echo "[ Wrn ] cargo-llvm-cov is not installed."
    echo "[ ==> ] To install cargo-llvm-cov, run:"
    echo "        rustup component add llvm-tools-preview"
    echo "        cargo install cargo-llvm-cov"
    exit 1
fi

echo "[ Ok  ] cargo-llvm-cov is installed."
echo "[ ==> ] Running code coverage metrics (excluding external libraries)..."

cd divoomd
cargo llvm-cov --all-targets
