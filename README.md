# Anno2205-Savegame-Modifier

Python script to view and modify your Anno 2205 savegames, including difficulty settings!

## Usage

First, clone this repository.

Then, locate your savefile:
- Windows (Ubisoft Connect): `C:\Program Files (x86)\Ubisoft\Ubisoft Game Launcher\savegames\8a362a1f-2f5b-4d43-aa8c-4a918a88771b\1253\`
- Lutris (Anno started through Ubisoft Connect): `~/Games/ubisoft-connect/drive_c/Program Files (x86)/Ubisoft/Ubisoft Game Launcher/savegames/8a362a1f-2f5b-4d43-aa8c-4a918a88771b/1253/`
- Wine: `${WINEPREFIX}/drive_c/Program Files (x86)/Ubisoft/Ubisoft Game Launcher/savegames/8a362a1f-2f5b-4d43-aa8c-4a918a88771b/1253/`

_The last two parts of the path (`8a362a1f-2f5b-4d43-aa8c-4a918a88771b/1253/`) may be different on your computer._

You do not need the file `1.save`. It only contains savefile metadata.

If you do not know which file is which savegame, use the `dump` command on them, which shows the name of your company.

**Please keep in mind that modifying you savefile might break it. It is a good idea to create a backup NOW!**

---

Command synopsis: `python3 anno2205_save.py <savegame-file> <command> [<flags>]`

### Inspecting the savefile

```bash
python3 anno2205_save.py <savefile> dump       # human-readable output
python3 anno2205_save.py <savefile> dump --csv # CSV output (section,field,value)
```

### Changing a difficulty settings in the savefile

```bash
python3 anno2205_save.py <savefile> set <field> <value>   # patch a difficulty field

# e.g. disable enemy invasions
python3 anno2205_save.py ./1774952996.save set DifficultyMilitaryInvasions 0
```

These settings can be modified:

| Setting name                                  | Description                                       | Possible values                                   | Tested/Working                 | 
|-----------------------------------------------|---------------------------------------------------|---------------------------------------------------|--------------------------------|
| `DifficultyConstructionCostRefund`            |                                                   |                                                   | not tested                     |
| `DifficultySatisfactionInfluencesTaxes`       | Satisfaction Impact                               | No Impact (0), Medium Impact (1), High Impact (2) | not tested                     |
| `DifficultyTemporarySectorEffects`            |                                                   |                                                   | not tested                     |
| `DifficultyConsumption`                       | Goods Consumption                                 | Sparse (0), Medium (1), Plenty (2)                | not tested                     |
| `DifficultyDominanceAgriculture`              |                                                   |                                                   | not tested                     |
| `DifficultyOptionalQuestTimeout`              |                                                   |                                                   | not tested                     |
| `DifficultyNpcLevelSpeed`                     |                                                   |                                                   | not tested                     |
| `DifficultyRevenue`                           |                                                   |                                                   | not tested                     |
| `DifficultyWorkforce`                         | Provided Workforce                                | Plenty (0), Medium (1), Sparse (2)                | not tested                     |
| `DifficultyTraderRefillRate`                  |                                                   |                                                   | not tested                     |
| `DifficultyDistributionCenterOutput`          | Unknown (seems to always be set to `1`)           | unknown                                           | not tested                     |
| `DifficultyMetropolisFactor`                  |                                                   |                                                   | not tested                     |
| `DifficultyMilitaryProgress`                  |                                                   |                                                   | not tested                     |
| `DifficultyPermanentSectorEffects`            |                                                   |                                                   | not tested                     |
| `DifficultyIncreasingDistributionCenterCosts` |                                                   |                                                   | not tested                     |
| `DifficultyMilitaryEnemyStrength`             |                                                   |                                                   | not tested                     |
| `DifficultyRelocateBuildings`                 |                                                   |                                                   | not tested                     |
| `DifficultyTradeRouteAdminCosts`              |                                                   |                                                   | not tested                     |
| `DifficultyOptionalQuestFrequency`            |                                                   |                                                   | not tested                     |
| `DifficultyDominanceHiTech`                   |                                                   |                                                   | not tested                     |
| `DifficultyDominanceHeavy`                    |                                                   |                                                   | not tested                     |
| `DifficultyDominanceEnergy`                   |                                                   |                                                   | not tested                     |
| `DifficultyDominanceBiotech`                  |                                                   |                                                   | not tested                     |
| `DifficultyDominanceShareBonus`               |                                                   |                                                   | not tested                     |
| `DifficultyInactiveCosts`                     |                                                   |                                                   | not tested                     |
| `DifficultyDestructibleShips`                 | Destroyed ships will get replaced with a unranked version | 0 (no), 1 (yes)                           | not tested                     |
| `DifficultyMilitaryProgress2`                 |                                                   |                                                   | not tested                     |
| `DifficultyMilitaryInvasions`                 | Enemy Invasions (Sector Invasion of Virgil Drake) | 0 (never), 1 (sparse)                             | tested, works                  |
| `DifficultyMilitaryEnemyStrength2`            |                                                   |                                                   | not tested                     |
| `DifficultyStartCredits`                      | Start Credits                                     | Plenty (0), Medium (1), Sparse (2)                | no effect when changed mid-game |
| `DifficultyFacilityAuctions`                  |                                                   |                                                   | not tested                     |
| `DifficultyTraderPrices`                      |                                                   |                                                   | not tested                     |

The `set` command will create a backup of the file, named `<orig-filename>.bak`, first.

**Please note, that not all properties have an effect when changed mid-game and will get overwritten!** Most of the settings are also untested, and I don't know which value matches which in-game string. So if you are interested in helping me finding all values, let me know!

---

After creating a modified savefile, reupload the file to Anno Savegame folder **and rename it, e.g. by incrementing the number by 1**.
If you do not rename the file, it will get overwritten by the cloud backup save file when starting up Anno (Ubisoft Cloud syncs saves by file name).

Have fun tinkering and playing :)

## Documentation

The results of reverse engineering the save file format are [documented in the wiki of this repository](https://code.leon.wtf/leon/Anno2205-Savegame-Modifier/wiki/File-Format-Specification).
