---
name: abnormal-return-model
description: Compute adjusted security, benchmark, abnormal, and cumulative abnormal returns using the approved method.
license: MIT
metadata:
  version: "1.0"
---

# Abnormal return model

Use adjusted close for the security and benchmark. For each trading day:

`security_return = current_security / previous_security - 1`

`benchmark_return = current_benchmark / previous_benchmark - 1`

`abnormal_return = security_return - benchmark_return`

Report units explicitly. Preserve full precision in machine output and round only in the
presentation layer. Do not describe abnormal return as causal proof.
