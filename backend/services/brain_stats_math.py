"""Statistical association scoring for the Brain Engine.

Replaces raw PMI (used by the original brain/ prototype) with the Dunning
(1993) log-likelihood ratio (G²) test, which does not get inflated by
low-frequency pairs the way raw PMI does.
"""
import math


def log_likelihood_ratio(count_ab: int, count_a: int, count_b: int, total: int) -> float:
    """G² log-likelihood ratio for the association between word a and word b.

    count_ab: number of times a and b co-occur
    count_a:  total occurrences of a in the corpus
    count_b:  total occurrences of b in the corpus
    total:    total word occurrences in the corpus
    """
    if count_ab <= 0 or count_a <= 0 or count_b <= 0 or total <= 0:
        return 0.0

    o11 = count_ab
    o12 = max(count_a - count_ab, 0)
    o21 = max(count_b - count_ab, 0)
    o22 = max(total - o11 - o12 - o21, 0)

    row1, row2 = o11 + o12, o21 + o22
    col1, col2 = o11 + o21, o12 + o22
    grand = row1 + row2

    if grand <= 0:
        return 0.0

    def expected(row_total: int, col_total: int) -> float:
        return (row_total * col_total) / grand

    cells = [
        (o11, expected(row1, col1)),
        (o12, expected(row1, col2)),
        (o21, expected(row2, col1)),
        (o22, expected(row2, col2)),
    ]

    g2 = 0.0
    for observed, exp in cells:
        if observed > 0 and exp > 0:
            g2 += observed * math.log(observed / exp)

    return round(2 * g2, 4)
