import pytest
from mqlkiscanner.parser import load_export, ORDERBOOK_HEADER

ROW = ['2026.07.15 18:47:42','Sell','0.00','GBPUSD','1.34950','','1.33578','2026.07.15 18:48:35','1.34950','','','0.00','close hedge by #1625580225']

def write(tmp_path, row):
    p=tmp_path/'hedge.csv'
    p.write_text(';'.join(ORDERBOOK_HEADER)+'\n'+';'.join(row)+'\n',encoding='utf-8')
    return str(p)

def test_exact_neutral_mt4_event_is_counted_separately(tmp_path):
    p=load_export(write(tmp_path,ROW))
    assert p.trades == []
    assert p.balances == []
    assert p.neutrale_hedge_metazeilen == 1

@pytest.mark.parametrize('index,value',[(2,'-0.1'),(4,'1.34951'),(4,'0'),(8,''),(9,'-0.01'),(10,'0.01'),(11,'-0.01'),(12,'close hedge by #x'),(12,'close hedge by #12 other'),(7,'2026.07.15 18:00:00'),(0,'broken'),(4,'NaN')])
def test_near_matches_remain_strict_errors(tmp_path,index,value):
    row=ROW.copy(); row[index]=value
    with pytest.raises(ValueError): load_export(write(tmp_path,row))

def test_cancelling_money_is_not_neutral_metadata(tmp_path):
    row=ROW.copy(); row[9]='-1'; row[11]='1'
    with pytest.raises(ValueError): load_export(write(tmp_path,row))

def test_positive_volume_remains_real_trade(tmp_path):
    row=ROW.copy(); row[2]='0.01'
    parsed=load_export(write(tmp_path,row))
    assert len(parsed.trades)==1
    assert parsed.neutrale_hedge_metazeilen==0

def test_wrong_width_remains_error(tmp_path):
    with pytest.raises(ValueError): load_export(write(tmp_path,ROW[:-1]))
