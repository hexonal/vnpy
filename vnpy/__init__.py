# The MIT License (MIT)

# Copyright (c) 2015-present, Xiaoyou Chen

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


# PEP 440 local version segment. This is upstream 4.4.0 plus the hexonal fork's
# own commits, and the suffix exists so that a run manifest can tell the two
# apart: `vnpy_alphakit/provenance.py` records `sys.modules["vnpy"].__version__`
# into every runs/*.json, and its other discriminator — a fingerprint over
# {symbols, row_count, span} — cannot see a change that only alters computed
# values. Without the suffix, two manifests straddling the vwap and rolling
# dtype corrections are byte-for-byte identical.
#
# The numeric suffix tracks `vnpy.alpha.semantics.FEATURE_SEMANTICS_VERSION`;
# bump both together, and roll both back together.
__version__ = "4.4.0+hexonal.2"
