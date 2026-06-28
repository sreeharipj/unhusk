header = """DUAL LICENSE NOTICE

This software is dual-licensed under the GNU Affero General Public License version 3 (AGPLv3) and a Commercial License.

1. GNU Affero General Public License version 3 (AGPLv3)
   You may use, distribute, and modify this software under the terms of the AGPLv3.
   See the full text of the AGPLv3 below.

2. Commercial License
   If you wish to use this software in a proprietary or commercial product without the restrictions of the AGPLv3, you must obtain a separate Commercial License.
   Please contact the repository owner for more information regarding commercial licensing.

==============================================================================
"""

with open("AGPL.txt", "r") as f:
    agpl = f.read()

with open("LICENSE", "w") as f:
    f.write(header + "\n" + agpl)
