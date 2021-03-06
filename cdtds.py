from adaptivewindow import AdaptiveWindow
from fptree import FPTree
from fptree import sort_transaction
from item import Item
from collections import Counter
import math
import sys

if sys.version_info[0] < 3:
    raise Exception("Python 3 or a more recent version is required.")


def tree_global_change(tree, other_item_count):
    assert(tree.is_sorted())
    change = 0.0
    for (path, count) in tree:
        sorted_path = sort_transaction(path, other_item_count)
        distance = levenstein_distance(path, sorted_path)
        change += (distance ** 2) / (len(path) ** 2)
    return change / tree.num_transactions


def variance(count, n):
    # Variance is defined as 1/n * E[(x-mu)^2]. We consider our X to be a
    # stream of n instances of [0,1] values; 1 if item appears in a transaction,
    # 0 if not. We know that the average is count/n, and that X is 1
    # count times, and 0 (n-count) times, so the variance then becomes:
    # 1/n * (count * (1 - support)^2 + (n-count) * (0 - support)^2).
    support = count / n
    return (count * (1 - support)**2 + (n - count) * (0 - support)**2) / n


def build_tree(window, item_count):
    path_len_sum = 0
    path_count = 0
    tree = FPTree()
    for bucket in window:
        for (transaction, count) in bucket.tree:
            sorted_transaction = sort_transaction(
                transaction, item_count)
            path_len_sum += count * len(sorted_transaction)
            path_count += count
            tree.insert(sorted_transaction, count)
    avg_path_len = path_len_sum / path_count
    return (tree, avg_path_len)


def find_concept_drift(
        window,
        min_cut_len,
        local_cut_confidence):
    # Find the index in bucket list where local drift occurs.
    if len(window) < 2:
        # Only one or less buckets, can't have drift.
        return (None, None)

    cut_index = len(window) - 2
    while cut_index >= 0:
        before_len = sum([len(bucket) for bucket in window[0:cut_index]])
        after_len = sum([len(bucket) for bucket in window[cut_index:]])

        # Ensure the candidate cut is a non-trivial length.
        if before_len < min_cut_len or after_len < min_cut_len:
            cut_index -= 1
            continue

        # Create a Counter() for the item frequencies before and after the
        # cut point.
        before_item_count = sum(
            [bucket.tree.item_count for bucket in window[0:cut_index]], Counter())
        after_item_count = sum(
            [bucket.tree.item_count for bucket in window[cut_index:]], Counter())

        # Check if any item's frequency has a significant difference.
        for item in after_item_count.keys():
            # Calculate "e local cut".
            before_support = before_item_count[item] / before_len
            after_support = after_item_count[item] / after_len

            n = before_support + after_support
            v = variance(n, before_len + after_len)
            m = 1 / ((1 / before_len) + (1 / after_len))
            delta_prime = math.log(
                2 * math.log(before_len + after_len) / local_cut_confidence)
            epsilon = (math.sqrt((2 / m) * v * delta_prime)
                       + (2 / (3 * m) * delta_prime))
            assert(epsilon >= 0 and epsilon <= 1)
            if abs(before_support -
                   after_support) >= epsilon:
                # Local drift.
                # Build tree to return to the mining algorithm.
                (tree, avg_path_len) = build_tree(
                    window[cut_index:], after_item_count)
                return (cut_index, tree)

        cut_index -= 1
    return (None, None)


def change_detection_transaction_data_streams(transactions,
                                              window_len,
                                              merge_threshold,
                                              min_cut_len,
                                              local_cut_confidence):
    assert(local_cut_confidence > 0 and local_cut_confidence <= 1)
    window = AdaptiveWindow(window_len, merge_threshold)
    num_transaction = 0
    for transaction in [list(map(Item, t)) for t in transactions]:
        num_transaction += 1

        # Insert transaction into bucket list. Bucket list will merge
        # buckets as necessary to maintain exponential histogram.
        if not window.add(transaction):
            # Not at a adaptive window bucket boundary.
            continue

        # At a adaptive window bucket boundary. Check for concept drift.
        (cut_index, tree) = find_concept_drift(
            window,
            min_cut_len,
            local_cut_confidence)
        if cut_index is None:
            continue

        # Otherwise we have concept drift, need to drop and mine.
        window[0:cut_index] = []
        yield (tree, num_transaction)
