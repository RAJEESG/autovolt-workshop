import os, re

for root, dirs, files in os.walk('templates'):
    for f in files:
        if f.endswith('.html'):
            p = os.path.join(root, f)
            with open(p, 'r', encoding='utf-8') as fp:
                txt = fp.read()
                matches = re.findall(r'href=[\"\']([^\"\']*(?:print|pdf)[^\"\']*)[\"\']', txt)
                matches += re.findall(r'window\.open\([\"\'`]([^\"\'`]+)[\"\'`]', txt)
                matches += re.findall(r'fetch\([\"\'`]([^\"\'`]*(?:print|pdf)[^\"\'`]*)[\"\'`]', txt)
                if matches:
                    print(f"{f}: {set(matches)}")
