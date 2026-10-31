import re

with open(r'C:\Users\mater\.minimax\sessions\mvs_4be75a039e3e4dd2a6a370720f28065c\workspace\qoi-repo\paper\aisc2027_unified_paper.tex', 'r', encoding='utf-8') as f:
    content = f.read()

# Use the exact string from the file
idx = content.find('16-Mode Discrimination Gap')
actual = content[idx:idx+500]
print('ACTUAL:')
print(repr(actual))

# Now do the replacement with the actual string
new_actual = r'\subsection{16-Mode Discrimination Gap}' + '\n\n' + r'The Brain vs. Creativity energy gap (1.85\%) requires $\sim$492k shots for 3-$\sigma$ statistical separation --- 481$\times$ current 1024. On open plan: $492\text{k shots} \times 0.74\text{ s/circuit} \approx 364\text{ s QPU}$ (single circuit time). \textbf{Fundamental limit:} open plan cannot resolve the mode competition quantum-mechanically; the shot-noise floor (0.137$\sigma$) is the primary barrier, not the quota.'

if actual in content:
    content = content.replace(actual, new_actual)
    with open(r'C:\Users\mater\.minimax\sessions\mvs_4be75a039e3e4dd2a6a370720f28065c\workspace\qoi-repo\paper\aisc2027_unified_paper.tex', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Replaced successfully')
else:
    print('Exact match failed')