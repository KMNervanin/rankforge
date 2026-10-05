# Field manual — The data observatory

## Make meaning explicit

A transformation is more than a loop over rows. It has an input contract, a normalization policy, an identity rule and an output contract. A report should explain rejected input instead of quietly hiding it.

The input is a list. Each valid row is a dictionary with a nonempty string `id`, a real calendar date in exact `YYYY-MM-DD` or `YYYY/MM/DD` format, and an amount string. Ignore extra fields. Dates use ASCII digits and must exist in the calendar.

Amounts use ASCII digits with an optional decimal point and one or two fractional digits. The per-row range is 0 through 9999999999999999.99 inclusive; leading zeros are allowed. Scientific notation, signs, spaces, NaN, infinity, `.50` and `1.` are outside this contract. A daily total may exceed the per-row maximum.

## Explore one row at a time

Run `python3 preview.py`. Predict the total before running it. Why are there two different day keys? Why is the first event counted again? Add a malformed row to your scratch input and decide what evidence you want to see.

## Exact arithmetic

Binary floating-point cannot represent every decimal amount exactly. `Decimal("0.10")` starts from the exact decimal text; constructing Decimal from a float preserves the float's earlier approximation. Keep amounts exact through aggregation and format the final result with two decimal places.

Decimal arithmetic also has a precision context: choose enough precision for the sum, not only for one row. Integer minor units are another valid approach. No numeric class or parser is mandatory. Test cents close to the stated maximum as well as small amounts.

## Identity and rejection

Normalize first, then compare an accepted identity's payload. `2024/02/29` and `2024-02-29` refer to the same day. `0.1` and `0.10` refer to the same amount. Keep the first accepted event, ignore an exact normalized replay, and reject a later conflict. A rejected invalid row does not reserve its id.

Return sorted day keys and two-decimal string totals. Return every rejected zero-based index exactly once, in any deterministic order. Preserve the input and return the same result on repeated calls. Existing saved manuals are preserved; the game's objectives contain the current contract.

## Explain the outcome

Choose one rejected row and explain the reason. Compare the old and new totals. State the check you used rather than simply saying the report looks right.
