import importlib
import unittest

from cogs.generateur import MODELES, valider_plan
from main import BlackstoneBot
from cogs.prefix_commands import PrefixCommands


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
            "cogs.prefix_commands",
        )
        for module in modules:
            with self.subTest(module=module):
                self.assertIsNotNone(importlib.import_module(module))

    def test_prefix_cog_exposes_all_feature_commands(self):
        bot = BlackstoneBot()
        cog = PrefixCommands(bot)
        names = {command.name for command in cog.get_commands()}
        expected = {
            "ping", "interdire", "autoriser", "regles", "mot_ajouter", "mot_retirer",
            "kick", "ban", "timeout", "clear", "rejoindre", "jouer", "pause",
            "reprendre", "passer", "stop", "quitter", "volume", "file",
            "protection_config", "avertissements", "avertissements_reset",
            "serveur_modeles", "serveur_modele", "serveur_demande", "serveur_annuler",
        }
        self.assertTrue(expected.issubset(names), f"Commandes manquantes : {expected - names}")

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
