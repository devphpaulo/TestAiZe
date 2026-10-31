"""Desktop capture host for TestAíZé. Pixels stay on this machine.

PT01: PySide6 grabs each screen before any overlay is shown.
PT02: stroke 4 px, font 18 px; annotations stay in bitmap space and are clipped by the crop.
PT03: Anexar, Copiar and Salvar leave the editor open. Cancel discards the draft.
      Nothing is restored after the process exits.
PT04: HTTP on 127.0.0.1 with an ephemeral header, never a URL or a log line.
PT05: the draft lives in memory. The saved evidence uses the session folder.
"""
