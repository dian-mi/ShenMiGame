
# placeholder engine_core with 43 roles support
class Role:
    def __init__(self, cid, name):
        self.cid = cid
        self.name = name
        self.alive = True

class GameEngine:
    def __init__(self):
        self.roles = {i: Role(i, f"角色{i}") for i in range(1,44)}
        self.logs = ["游戏开始"]

    def next_turn(self):
        self.logs.append("下一回合")
