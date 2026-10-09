# Règles de confidentialité

Tamis est une application qui cherche des offres d'emploi sur le web et ne garde que celles qui correspondent à votre CV. Cette page explique quelles données elle utilise, pourquoi, et comment les supprimer.

## Qui est responsable de vos données

L'application est un projet personnel, exploité par un particulier. Pour toute question ou demande concernant vos données : {contact}.

## Données enregistrées

- **Votre adresse e-mail Google**, pour vous reconnaître d'une connexion à l'autre. Votre nom et votre photo de profil, transmis par Google à la connexion, ne sont pas enregistrés sur le serveur : ils sont gardés dans le cookie de votre session, pour afficher votre vignette. La photo elle-même est chargée depuis les serveurs de Google.
- **Le texte de votre CV, dont vos coordonnées sont retirées** : adresse e-mail, téléphone, liens, adresse postale, date de naissance et, quand il est connu, votre nom. Ce retrait est automatique : il reconnaît ces informations à leur forme, sans garantie d'en trouver toutes les mentions. Le fichier PDF que vous déposez n'est pas conservé : il est lu une fois, pour en tirer ce texte.
- **Vos recherches** : les phrases de recherche, les types de contrat et les lieux que vous enregistrez.
- **Les offres trouvées pour vous** : titre, lien, extrait, type de contrat et lieu lus sur l'annonce, raison pour laquelle l'offre a été retenue, et le suivi que vous en faites : candidature envoyée, entretien obtenu, refus de l'employeur, avec la date de chaque étape, et offre supprimée.
- **Les pages écartées** : titre, lien, type de contrat et lieu lus sur la page, raison du rejet et critères en défaut, pour ne pas les évaluer une seconde fois.
- **Le bilan de chaque recherche lancée** : sa date, pour appliquer la limite quotidienne, et des mesures techniques (nombre de pages trouvées, retenues et écartées, durée, volume de texte échangé avec OpenAI), pour suivre le coût et le bon fonctionnement du service. Les administrateurs de l'application voient, pour chaque compte, son adresse e-mail et le total de ces mesures ; ils ne voient ni vos recherches, ni votre CV, ni les pages trouvées pour vous.
- **Le journal des pages évaluées** : pour chaque page lue lors d'une recherche, retenue ou non, son titre, son lien, ce qui y a été lu (type de contrat, lieu, mode de travail), le verdict critère par critère et sa raison. Il sert à comprendre et à corriger le tri. Contrairement aux pages écartées, il n'est pas effacé quand vous remplacez votre CV.
- **Les appels au moteur de recherche** : pour chaque recherche envoyée à Tavily, le texte envoyé, tiré de vos postes recherchés, et le nombre de pages qu'elle a ramenées, déjà connues, évaluées et retenues. Ils servent à savoir ce que chaque poste recherché rapporte et coûte.
- **Vos corrections du tri** : quand vous remettez une page écartée dans vos offres, ou quand vous supprimez une offre, l'application en garde la trace : le titre et le lien de la page, le verdict qui avait été rendu, et le motif de la suppression si vous en choisissez un. Elles servent à mesurer si le tri se trompe, et sur quoi.
- **Les erreurs que vous rencontrez** : quand l'application refuse une demande ou tombe en panne, elle note l'opération demandée, le type de l'erreur, sa date et votre compte, jamais ce que vous aviez envoyé ni le message de l'erreur. Il en va de même quand une page de l'application rencontre une erreur dans votre navigateur : celui-ci signale le type de l'erreur, l'écran concerné et l'endroit du programme où elle s'est produite, jamais ce que la page affichait. Ces lignes servent à repérer et à corriger les pannes ; elles sont effacées au bout de {server_error_days} jours. Les administrateurs n'en voient que des totaux, sans savoir quel compte est concerné.
- **La date de votre dernière utilisation**, au jour près, pour supprimer les comptes qui ne servent plus.

L'application n'utilise aucun outil de mesure d'audience ni de publicité. Elle dépose un seul cookie, nécessaire pour maintenir votre connexion. Votre choix de thème, clair ou sombre, est gardé dans votre navigateur et n'est pas envoyé au serveur. L'écran de connexion affiche le bouton « Se connecter avec Google », chargé depuis les serveurs de Google, qui peut déposer ses propres cookies.

## À quoi servent ces données

Uniquement à faire fonctionner le service : vous connecter, chercher des offres, les comparer à votre CV et vous présenter le résultat. Elles ne sont ni vendues, ni utilisées à des fins publicitaires, ni visibles par les autres utilisateurs.

Ce traitement repose sur l'exécution du service que vous demandez en vous connectant (article 6.1.b du RGPD) : sans ces données, l'application ne peut ni chercher ni trier d'offres pour vous.

## À qui elles sont transmises

- **Google**, pour la connexion. L'application reçoit de Google votre adresse e-mail et les informations de base de votre profil.
- **OpenAI**, pour évaluer les offres. À chaque recherche, le texte de votre CV sans vos coordonnées, vos phrases de recherche et leurs lieux sont envoyés à OpenAI avec le contenu de chaque page d'offre à évaluer.
- **Tavily**, pour la recherche web. Seules vos phrases de recherche, avec leur type de contrat et leur lieu, lui sont envoyées, pas votre CV.
- **Fly.io** (Fly.io, Inc., 2261 Market Street #4990, San Francisco, CA 94114, États-Unis), qui héberge l'application et sa base de données, dans la région de Paris.

Quand une recherche échoue ou que l'application tombe en panne, son administrateur peut en être prévenu par le service de notifications ntfy. Ce message ne contient rien qui vous concerne : seulement le type de l'incident et des nombres.

Ces quatre sociétés sont établies aux États-Unis. Les données hébergées par Fly.io restent dans la région de Paris ; les transmissions à OpenAI, Tavily et Google impliquent un transfert de données hors de l'Union européenne. Google et Fly.io adhèrent au cadre de protection des données UE-États-Unis (Data Privacy Framework). Les transferts d'OpenAI hors de l'Union européenne sont encadrés par les clauses contractuelles types de la Commission européenne, prévues par son accord de traitement des données.

## Durée de conservation

Vos données sont conservées tant que vous utilisez l'application. Un compte resté {inactive_months} mois sans utilisation est supprimé automatiquement, avec tout ce qu'il contient : adresse e-mail, CV, recherches, offres, pages écartées, bilans des recherches, journal des pages évaluées, appels au moteur de recherche, erreurs rencontrées et corrections du tri. Vous n'en êtes pas prévenu, l'application n'envoyant aucun e-mail.

À la suppression d'un compte, par vous ou automatiquement, une seule chose est conservée : le total, par mois, de ce que ses recherches ont consommé (nombre de recherches, de pages lues et volume de texte échangé avec OpenAI et Tavily). Ces totaux ne portent ni adresse e-mail, ni contenu, ni date précise : ils ne permettent pas de vous identifier, et servent uniquement à connaître le coût du service dans la durée.

Si votre accès est retiré, vous ne pouvez plus vous connecter : votre compte est supprimé au terme de ce même délai, ou plus tôt si vous le demandez. Tant que vous avez accès à l'application, vous pouvez supprimer votre compte vous-même.

Avant certaines mises à jour de l'application, une copie de sauvegarde de la base de données est faite et conservée au même endroit. La suppression d'un compte retire aussi ses données de ces copies.

## Vos droits

Conformément au règlement général sur la protection des données (RGPD), vous pouvez demander l'accès à vos données, leur rectification ou leur suppression, en recevoir une copie dans un format courant (portabilité), et demander la limitation de leur traitement ou vous y opposer, en écrivant à l'adresse indiquée plus haut. Une réponse vous est donnée dans un délai d'un mois. La suppression porte sur l'ensemble de votre compte : adresse e-mail, CV, recherches, offres, pages écartées, bilans des recherches, journal des pages évaluées, appels au moteur de recherche, erreurs rencontrées et corrections du tri.

Vous pouvez supprimer votre compte vous-même, depuis la page « Compte » de l'application : votre adresse e-mail, votre CV, vos recherches, vos offres, les pages écartées, les bilans de vos recherches, le journal des pages évaluées, les appels au moteur de recherche, les erreurs rencontrées et vos corrections du tri sont alors effacés immédiatement, sans retour possible. Vous pouvez aussi remplacer votre CV et supprimer vos recherches sans supprimer votre compte. Vous pouvez aussi retirer l'accès de l'application à votre compte Google depuis les paramètres de sécurité de ce compte.

Si vous estimez que vos droits ne sont pas respectés, vous pouvez adresser une réclamation à la CNIL (www.cnil.fr).

## Modifications

Ces règles peuvent évoluer avec l'application. La version en vigueur est celle affichée sur cette page.
