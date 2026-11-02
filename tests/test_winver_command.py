"""La orden de PowerShell que mira la firma de un ejecutable (se prueba en cualquier sistema)."""

from bootscout.winver import signature_command


def test_path_is_passed_as_data_not_as_script():
    # Un nombre de archivo puesto por un malware no puede convertirse en código de PowerShell.
    evil = r"C:\apps\x'; Write-Output 'INJECTED'; #.exe"
    args, env = signature_command(evil)
    assert all(evil not in a and "INJECTED" not in a for a in args)
    assert env["BOOTSCOUT_PATH"] == evil
    assert "-LiteralPath $env:BOOTSCOUT_PATH" in args[-1]


def test_apostrophes_in_normal_names_are_fine():
    args, env = signature_command(r"C:\Program Files\O'Reilly\reader.exe")
    assert "O'Reilly" not in args[-1] and env["BOOTSCOUT_PATH"].endswith("reader.exe")
