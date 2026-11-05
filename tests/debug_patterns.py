import re

text = "Create a file called orbit_data/test_nl1.txt with hello world"
text_lower = text.lower()

file_ops = [
    "read file",
    "write file",
    "create file",
    "create a file",
    "edit file",
    "list files",
    "list directory",
    "show files",
    "file info",
    "copy file",
    "delete file",
    "search files",
    "read pdf",
    "make a file",
    "save to file",
    "save file",
]

print("Text:", text_lower)
print()
for op in file_ops:
    if op in text_lower:
        print(f'MATCH: "{op}" found in text')
print()

# Test regex
m = re.search(
    r"(?:create|write|make)\s+(?:a\s+)?(?:file\s+)?(?:called\s+|named\s+)?[`\"']?([^\s`\"']+)[`\"']?\s+(?:with|containing)\s+[`\"']?(.+?)[`\"']?\s*$",
    text,
    re.IGNORECASE,
)
if m:
    print(f"Regex match: path={m.group(1)}, content={m.group(2)}")
else:
    print("No regex match")

# Test all messages
messages = [
    "Create a file called orbit_data/test_nl1.txt with hello world",
    "Create orbit_data/test_nl2.txt containing test content",
    "Write orbit_data/test_nl3.txt with some data here",
    "Make a file called orbit_data/test_nl4.txt with python code",
]

print("\n--- All Messages ---")
for msg in messages:
    ml = msg.lower()
    matched = any(op in ml for op in file_ops)
    m = re.search(
        r"(?:create|write|make)\s+(?:a\s+)?(?:file\s+)?(?:called\s+|named\s+)?[`\"']?([^\s`\"']+)[`\"']?\s+(?:with|containing)\s+[`\"']?(.+?)[`\"']?\s*$",
        msg,
        re.IGNORECASE,
    )
    print(f"{msg[:55]}")
    print(f"  file_ops match: {matched}")
    print(f"  regex match: {m.group(1) if m else 'NONE'}")
    print()
