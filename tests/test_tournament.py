from pathlib import Path
from emulation.tournament import Ledger


def test_history_survives_restart(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    engines = ledger.state['engines']
    white, black = ledger.pending(engines)[0]
    directory = ledger.start(white, black)
    ledger.finish(directory, None, 'timeout')
    ledger = Ledger(tmp_path)
    assert (white, black) in ledger.pending(engines)
    directory = ledger.start(white, black)
    ledger.finish(directory, '1-0', None)
    ledger = Ledger(tmp_path)
    assert (white, black) not in ledger.pending(engines)
    assert ledger.ranking(engines)[0]['engine'] == white
    assert ledger.ranking(engines)[0]['points'] == 1
    assert len(ledger.state['pairings'][0]['attempts']) == 2
