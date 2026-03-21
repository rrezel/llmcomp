"""
Generate dictionary + pre-made challenges.

1. Generate 900,000 random base words (20-100 letters)
2. For each of 100 challenges, random-walk 50 steps, adding new words to dictionary
3. Pad remaining slots to exactly 1,000,000 with random words
4. Write dictionary.txt and challenges.txt
"""
import random
import string

TARGET_TOTAL = 1_000_000
NUM_BASE_WORDS = 900_000
MIN_LEN = 40
MAX_LEN = 60
NUM_CHALLENGES = 100
PATH_LENGTH = 300

random.seed(42)

print("Generating base dictionary...")
dictionary = set()
while len(dictionary) < NUM_BASE_WORDS:
    length = random.randint(MIN_LEN, MAX_LEN)
    word = ''.join(random.choices(string.ascii_uppercase, k=length))
    dictionary.add(word)

print(f"Base dictionary: {len(dictionary)} words")


def random_change(word):
    i = random.randrange(len(word))
    c = random.choice(string.ascii_uppercase)
    while c == word[i]:
        c = random.choice(string.ascii_uppercase)
    return word[:i] + c + word[i+1:]


def random_add(word):
    if len(word) >= MAX_LEN:
        return None
    i = random.randrange(len(word) + 1)
    c = random.choice(string.ascii_uppercase)
    return word[:i] + c + word[i:]


def random_remove(word):
    if len(word) <= MIN_LEN:
        return None
    i = random.randrange(len(word))
    return word[:i] + word[i+1:]


def random_step(word):
    ops = [random_change, random_add, random_remove]
    random.shuffle(ops)
    for op in ops:
        result = op(word)
        if result is not None:
            return result
    return random_change(word)


print(f"Generating {NUM_CHALLENGES} challenges of {PATH_LENGTH} steps...")
challenges = []
words_before = len(dictionary)

for i in range(NUM_CHALLENGES):
    start = random.choice(list(dictionary))
    current = start
    path = [current]

    for step in range(PATH_LENGTH):
        found_existing = False
        for _ in range(10):
            candidate = random_step(current)
            if candidate in dictionary and candidate not in path:
                current = candidate
                path.append(current)
                found_existing = True
                break

        if not found_existing:
            current = random_step(current)
            dictionary.add(current)
            path.append(current)

    challenges.append((start, current))
    if (i + 1) % 10 == 0:
        print(f"  [{i+1}/{NUM_CHALLENGES}] dict size: {len(dictionary)}")

path_words_added = len(dictionary) - words_before
print(f"After challenges: {len(dictionary)} words ({path_words_added} added from paths)")

# Pad to exactly 1,000,000
padding_needed = TARGET_TOTAL - len(dictionary)
if padding_needed > 0:
    print(f"Padding with {padding_needed} random words...")
    while len(dictionary) < TARGET_TOTAL:
        length = random.randint(MIN_LEN, MAX_LEN)
        word = ''.join(random.choices(string.ascii_uppercase, k=length))
        dictionary.add(word)

print(f"Final dictionary size: {len(dictionary)}")
assert len(dictionary) == TARGET_TOTAL, f"Expected {TARGET_TOTAL}, got {len(dictionary)}"

print("Shuffling and writing dictionary.txt...")
dict_list = list(dictionary)
random.shuffle(dict_list)
with open("dictionary.txt", "w") as f:
    for word in dict_list:
        f.write(word + "\n")

print("Writing challenges.txt...")
with open("challenges.txt", "w") as f:
    for start, goal in challenges:
        f.write(f"{start},{goal}\n")

print("Done.")
