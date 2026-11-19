import re

text = """GRE a i fy
a a a
Meta
SHREE MITHAI PRIVATE LIMITED
NO.189, Al BLOCK, Iv AVE, ANNA NAGAR,
CHENNAI-600040, PHONE: 044-28282828
FSSAI LIC No: 12414062900936
GSTIN ; BEAABCS5 166P1ZY

** INVOICE**
Doc No.: ANI/2627/ 143259
User: ANNASWT2

ee we ene meme ee
ee ee
W-“—w ww

16: 27 22-09-2026
a RAJEEV KUMAR

-- am
—~_wawe eer Vwrrrmtrn ~

1. 000 20. 00 50.00

we ee nee ee tere Ts
ee leraneuageginsyssis2:
-— ~~ ewe oe
ww ea

-_—-eer er = Soa

Sub Total

oucput CGST :
Output $G$] a

we: e~

-otr ~~
o-
a ne
-
~o
ad

Total
(Rupe

es Fifty Three’ ‘Say? |
rsyR: 53. 00"""

def clean_ocr_text(text):
    cleaned_lines = []
    
    # Common characters that Tesseract hallucinates from dashed lines
    junk_chars = set('ewmrn-_~=.,;:"\'|[](){} ')
    
    for line in text.split('\n'):
        original_line = line
        line = line.strip()
        if not line:
            continue
            
        alnum_chars = [c for c in line if c.isalnum()]
        if len(alnum_chars) < 2:
            continue
            
        # Count how many characters are "junk"
        junk_count = sum(1 for c in line.lower() if c in junk_chars)
        
        # If the line is more than 60% junk, and it's not a valid number, discard it.
        # But wait, "Sub Total" has 9 chars, 1 space. Junk ratio is 1/9 = 11%
        # "ee we ene meme ee" has 17 chars, all in junk_chars! Junk ratio = 100%
        # "1. 000 20. 00 50.00" has numbers, but spaces and dots are junk. Length 19, junk = 8. Ratio = 42%.
        if junk_count / len(line) > 0.65:
            # Maybe it's a number?
            if len(alnum_chars) < 4:
                continue
                
            # If it's mostly junk, but has some letters, check if letters are ONLY e, w, m, r, n, a, i, t, s
            only_garbage_letters = all(c.lower() in 'ewmrnaits' for c in alnum_chars if c.isalpha())
            if only_garbage_letters:
                continue
        
        # Another check: words that are just repeating letters
        words = line.split()
        is_garbage = True
        for w in words:
            if len(w) >= 3 and any(c.isalnum() for c in w) and not all(c.lower() in 'ewmrn-_~' for c in w):
                is_garbage = False
                break
        
        # Numbers are not garbage
        if any(c.isdigit() for c in line):
            is_garbage = False
            
        if is_garbage and len(words) > 0:
            continue

        cleaned_lines.append(original_line.strip())
        
    return '\n'.join(cleaned_lines)

print(clean_ocr_text(text))
