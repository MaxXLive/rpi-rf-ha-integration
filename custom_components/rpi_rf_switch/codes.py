"""PT2262 code calculation and decoding for DIP-switch based 433 MHz outlets."""


def calc_pt2262_code(system_code: str, unit_code: str, command: bool) -> int:
    """Calculate PT2262 decimal code from system code and unit code.

    This implements the encoding used by most common 433 MHz outlets
    (Brennenstuhl, Mumbi, Etekcity, etc.) with DIP switches.

    The PT2262 uses 12 tribits (tri-state bits):
    - Tribits 1-5:  System code (DIP switches 1-5)
    - Tribits 6-10: Unit code (buttons A-E)
    - Tribits 11-12: Command (ON/OFF)

    Each tribit maps to 2 binary bits:
    - '0' -> 00
    - 'F' (float) -> 01
    - '1' -> 11

    Args:
        system_code: 5-char string of '0' and '1' (DIP switch positions)
        unit_code: Single char 'A'-'E' (unit button)
        command: True for ON, False for OFF

    Returns:
        Decimal code to send via rpi-rf
    """
    tribits: list[str] = []

    # System code: DIP ON='0', DIP OFF='F'
    for bit in system_code:
        tribits.append("0" if bit == "1" else "F")

    # Unit code: selected='0', others='F'
    unit_index = ord(unit_code.upper()) - ord("A")
    for i in range(5):
        tribits.append("0" if i == unit_index else "F")

    # Command: ON='0F', OFF='F0'
    if command:
        tribits.extend(["0", "F"])
    else:
        tribits.extend(["F", "0"])

    # Convert tribits to 24-bit binary string
    tribit_to_bin = {"0": "00", "F": "01", "1": "11"}
    binary = "".join(tribit_to_bin[t] for t in tribits)

    return int(binary, 2)


def decode_pt2262_code(code: int) -> dict | None:
    """Try to reverse-engineer PT2262 system/unit codes from a decimal code.

    Returns dict with system_code, unit_code, command if valid PT2262,
    or None if the code doesn't match PT2262 encoding.
    """
    if code < 0 or code > 0xFFFFFF:
        return None

    binary = format(code, "024b")

    tribit_map = {"00": "0", "01": "F", "11": "1"}
    tribits: list[str] = []
    for i in range(0, 24, 2):
        pair = binary[i : i + 2]
        if pair not in tribit_map:
            return None
        tribits.append(tribit_map[pair])

    # System code (tribits 0-4): must be '0' or 'F' only
    system_tribits = tribits[:5]
    if any(t == "1" for t in system_tribits):
        return None

    # Unit code (tribits 5-9): exactly one '0', rest 'F'
    unit_tribits = tribits[5:10]
    if unit_tribits.count("0") != 1 or any(t == "1" for t in unit_tribits):
        return None

    # Command (tribits 10-11): '0F' = ON, 'F0' = OFF
    cmd = tribits[10:12]
    if cmd == ["0", "F"]:
        command = True
    elif cmd == ["F", "0"]:
        command = False
    else:
        return None

    # Decode: tribit '0' → DIP ON (1), tribit 'F' → DIP OFF (0)
    system_code = "".join("1" if t == "0" else "0" for t in system_tribits)
    unit_code = chr(ord("A") + unit_tribits.index("0"))

    return {
        "system_code": system_code,
        "unit_code": unit_code,
        "command": command,
    }
