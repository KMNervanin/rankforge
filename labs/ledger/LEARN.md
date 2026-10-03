# Field manual — The data observatory

## Make meaning explicit

A transformation is more than a loop over rows. It has an input contract, a normalization policy, an identity rule and an output contract. A report should explain rejected input instead of quietly hiding it.

The accepted date formats are exact `YYYY-MM-DD` and `YYYY/MM/DD`. The amount is an ordinary decimal string: digits with an optional decimal point and one or two fractional digits. Scientific notation, signs, spaces, NaN and infinity are outside this contract. Zero is allowed.

## Explore one row at a time

Run `python3 preview.py`. Predict the total before running it. Why are there two different day keys? Why is the first event counted again? Add a malformed row to your scratch input and decide what evidence you want to see.

## Exact arithmetic

Binary floating-point cannot represent every decimal amount exactly. `Decimal("0.10")` starts from the exact decimal text; constructing Decimal from a float preserves the float's earlier approximation. Keep amounts exact through aggregation and format the final result with two decimal places.

## Identity and rejection

Normalize first, then compare an accepted identity's payload. `2024/02/29` and `2024-02-29` refer to the same day. `0.1` and `0.10` refer to the same amount. Keep the first accepted event, ignore an exact normalized replay, and reject a later conflict. A rejected invalid row does not reserve its id.

## Explain the outcome

Choose one rejected row and explain the reason. Compare the old and new totals. State the check you used rather than simply saying the report looks right.
