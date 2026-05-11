"""PT2262 code calculation for DIP-switch based 433 MHz outlets."""


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

    # Command: ON='FF', OFF='F0'
    if command:
        tribits.extend(["F", "F"])
    else:
        tribits.extend(["F", "0"])

    # Convert tribits to 24-bit binary string
    tribit_to_bin = {"0": "00", "F": "01", "1": "11"}
    binary = "".join(tribit_to_bin[t] for t in tribits)

    return int(binary, 2)
