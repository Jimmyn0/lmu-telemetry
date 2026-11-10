"""Le groupe : partager ses performances en ligne avec ses amis, et recevoir les leurs.

Un petit service sur Cloudflare (`service/`, voir docs/20-groupe.md) garde ce que les
membres d'un groupe partagent. Ce paquet en est le client :

* `reglages` : l'adresse du service, et la place de ce PC dans un groupe ;
* `service` : les requêtes au service ;
* `synchro` : la copie du groupe gardée sur ce PC, et la synchronisation en tâche de fond.
"""
