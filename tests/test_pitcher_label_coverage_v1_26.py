import unittest
from pitcher_label_coverage_v1_26 import boxscore, classify, schedule, standings


def game(pk=3,state='Final',score=2):
    return dict(gamePk=pk,gameType='R',season='2024',
                status=dict(abstractGameState='Final',detailedState=state),
                teams={'away':dict(team=dict(id=1),score=score),
                       'home':dict(team=dict(id=2),score=1)})


class CoverageTests(unittest.TestCase):
    def test_makeup_games_and_standings_totals(self):
        games=[game(state='Postponed'),game(),game()]
        d=dict(dates=[dict(games=games)])
        result,ok,_,_=schedule(d,2024,{1:1,2:1})
        self.assertEqual(result,{3:(1,2)})
        self.assertTrue(ok)
        self.assertFalse(schedule(d,2024,{1:2,2:2})[1])
        games.append(game(score=4))
        with self.assertRaises(ValueError):
            schedule(d,2024,{1:1,2:1})

    def test_requires_all_30_standings_teams(self):
        with self.assertRaises(ValueError):
            standings(dict(records=[dict(league=dict(id=103),teamRecords=[])]),2024)

    def test_zero_out_pitcher_counts_as_appearance(self):
        def team(t,p,q):
            return dict(team=dict(id=t),pitchers=[p,q],players={
                str(n):dict(person=dict(id=n),stats=dict(pitching=dict(inningsPitched=ip,gamesPitched=1)))
                for n,ip in [(p,'0.0'),(q,'9.0')]},
                teamStats=dict(pitching=dict(inningsPitched='9.0')))
        d=dict(teams=dict(away=team(1,11,12),home=team(2,21,22)))
        self.assertEqual(boxscore(d,(1,2)),{11,12,21,22})
        line=d['teams']['away']['players']['11']['stats']['pitching']
        line['gamesPitched']=0
        self.assertEqual(boxscore(d,(1,2)),{12,21,22})
        line['battersFaced']=1
        with self.assertRaises(ValueError):
            boxscore(d,(1,2))
        del line['battersFaced']
        d['teams']['away']['pitchers'].remove(11)
        with self.assertRaises(ValueError):
            boxscore(d,(1,2))
        del d['teams']['away']['players']['11']
        d['teams']['away']['teamStats']['pitching']['inningsPitched']='9.1'
        with self.assertRaises(ValueError):
            boxscore(d,(1,2))

    def test_zero_requires_both_completeness_and_identity(self):
        self.assertEqual(classify(1,None,None,{},True,{1}),('VERIFIED_NO_APPEARANCE',0))
        for ok,ids in [(False,{1}),(True,set()),(False,set())]:
            self.assertEqual(classify(1,None,None,{},ok,ids)[1],None)
        self.assertEqual(classify(1,None,12,{},True,{1}),('CONFLICT',None))
        self.assertEqual(classify(1,None,0,{1:1},True,set()),('VERIFIED_APPEARED',1))
        self.assertEqual(classify(1,None,0,{1:1},False,set()),('VERIFIED_APPEARED',None))


if __name__=='__main__':
    unittest.main()
