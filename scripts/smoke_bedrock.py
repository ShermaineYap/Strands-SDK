"""First thing to run with AWS credentials: one real Nova call through the writer.

    export AWS_REGION=ap-southeast-1
    python scripts/smoke_bedrock.py

Prints the model's FloodBrief, the verifier verdict, token usage and estimated cost.
If the first draft is rejected, it retries with the verifier's feedback (max 3),
exactly as the graph does.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.eval_verifier import scenario  # noqa: E402
from jagasungai.compose import compose_message  # noqa: E402
from jagasungai.graph import MAX_ATTEMPTS, NOVA_2_LITE_USD_PER_M  # noqa: E402
from jagasungai.verify import verify  # noqa: E402
from jagasungai.writer import DEFAULT_MODEL_ID, DEFAULT_REGION, make_model, write_brief  # noqa: E402


def main() -> None:
    a, _ = scenario()
    model = make_model()
    print(f"model {DEFAULT_MODEL_ID} in {DEFAULT_REGION}")
    feedback, tin, tout = None, 0, 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        brief, usage = write_brief(model, a, feedback)
        tin += usage.get("inputTokens", 0)
        tout += usage.get("outputTokens", 0)
        res = verify(brief, a)
        print(f"\n--- attempt {attempt}: verifier {'PASS' if res.ok else 'REJECT'}")
        if res.ok:
            print(compose_message(brief, a, "Kelantan"))
            break
        print(res.feedback())
        feedback = res.feedback()
    cost = (tin * NOVA_2_LITE_USD_PER_M[0] + tout * NOVA_2_LITE_USD_PER_M[1]) / 1e6
    print(f"\ntokens in {tin}, out {tout}, est. cost US${cost:.5f}")


if __name__ == "__main__":
    main()
