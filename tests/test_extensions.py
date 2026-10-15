import importlib
import unittest

from cogs.generateur import MODELES, valider_plan
from main import BlackstoneBot


class ExtensionTests(unittest.TestCase):
    def test_bot_can_be_constructed(self):
        bot = BlackstoneBot()
        self.assertIsNotNone(bot.tree)

    def test_all_extensions_import(self):
        modules = (
            "cogs.automod",
            "cogs.general",
            "cogs.generateur",
            "cogs.moderation",
            "cogs.musique",
            "cogs.protection",
        )
        for module in modules:
            with self.subTest(module=module):
                self.assertIsNotNone(importlib.import_module(module))

    def test_all_server_templates_pass_validation(self):
        for key, modele in MODELES.items():
            with self.subTest(modele=key):
                plan, avertissements = valider_plan(modele["plan"])
                self.assertTrue(plan["roles"])
                self.assertTrue(plan["categories"])
                self.assertLessEqual(len(plan["roles"]), 25)
                self.assertLessEqual(len(plan["categories"]), 15)
                self.assertLessEqual(
                    sum(len(categorie["salons"]) for categorie in plan["categories"]),
                    80,
                )


if __name__ == "__main__":
    unittest.main()
