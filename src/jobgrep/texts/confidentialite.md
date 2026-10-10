# Règles de confidentialité

JobGrep est une application qui cherche des offres d'emploi sur le web et ne garde que celles qui correspondent à votre CV. Cette page explique quelles données elle utilise, pourquoi, et comment les supprimer.

## Qui est responsable de vos données

L'application est un projet personnel, exploité par Guillaume Legall, un particulier. C'est lui le responsable du traitement de vos données. Pour toute question ou demande concernant vos données : {contact}.

## Données enregistrées

- **Votre adresse e-mail Google**, pour vous reconnaître d'une connexion à l'autre. Votre nom et votre photo de profil, transmis par Google à la connexion, ne sont pas enregistrés sur le serveur : ils sont gardés dans le cookie de votre session, pour afficher votre vignette. La photo elle-même est chargée depuis les serveurs de Google.
- **Pour un essai sans compte, aucune adresse e-mail** : l'essai n'est reconnu que par le cookie de votre navigateur. À son ouverture, l'application garde une empreinte de votre adresse IP, calculée de façon à ne pas pouvoir retrouver l'adresse, pour limiter le nombre d'essais ouverts par jour depuis une même connexion. Cette empreinte n'est pas rattachée à votre essai, et elle est effacée au bout de {trial_start_hours} heures.
- **Le texte de votre CV, dont vos coordonnées sont retirées** : adresse e-mail, téléphone, liens, adresse postale, date de naissance et, quand il est connu, votre nom. Pour un essai sans compte, votre nom n'est pas connu de l'application : il n'est donc pas retiré. Ce retrait est automatique : il reconnaît ces informations à leur forme, sans garantie d'en trouver toutes les mentions. Le fichier PDF que vous déposez n'est pas conservé : il est lu une fois, pour en tirer ce texte.
- **Vos recherches** : les phrases de recherche, les types de contrat et les lieux que vous enregistrez.
- **Les offres trouvées pour vous** : titre, lien, extrait, type de contrat et lieu lus sur l'annonce, raison pour laquelle l'offre a été retenue, et le suivi que vous en faites : annonce ouverte depuis l'application, candidature envoyée, entretien obtenu, refus de l'employeur, avec la date de chaque étape, et offre supprimée.
- **Les pages écartées** : titre, lien, type de contrat et lieu lus sur la page, raison du rejet et critères en défaut, pour ne pas les évaluer une seconde fois.
- **Le bilan de chaque recherche lancée** : sa date, pour appliquer la limite quotidienne, et des mesures techniques (nombre de pages trouvées, retenues et écartées, durée, volume de texte échangé avec OpenAI), pour suivre le coût et le bon fonctionnement du service. Les administrateurs de l'application voient, pour chaque compte, son adresse e-mail, le total de ces mesures, et où il en est : si un CV est déposé, le nombre de postes recherchés, d'offres retenues, d'annonces ouvertes, de candidatures, d'entretiens et de corrections, les jours où vous êtes venu, et la suite datée de ces actions et des erreurs rencontrées. Ils voient aussi combien de pages ont été écartées pour chaque raison (métier, compétences, niveau, contrat, lieu). Cela leur sert à comprendre où l'application vous bloque. Ils ne voient ni le contenu de vos recherches, ni votre CV, ni l'intitulé ou le lien des pages trouvées pour vous.
- **Le journal des pages évaluées** : pour chaque page lue lors d'une recherche, retenue ou non, son titre, son lien, ce qui y a été lu (type de contrat, lieu, mode de travail), le verdict critère par critère et sa raison. Il sert à comprendre et à corriger le tri. Contrairement aux pages écartées, il n'est pas effacé quand vous remplacez votre CV.
- **Les appels au moteur de recherche** : pour chaque recherche envoyée à Tavily, le texte envoyé, tiré de vos postes recherchés, et le nombre de pages qu'elle a ramenées, déjà connues, évaluées et retenues. Ils servent à savoir ce que chaque poste recherché rapporte et coûte.
- **Vos corrections du tri** : quand vous remettez une page écartée dans vos offres, ou quand vous supprimez une offre, l'application en garde la trace : le titre et le lien de la page, le verdict qui avait été rendu, et le motif de la suppression si vous en choisissez un. Elles servent à mesurer si le tri se trompe, et sur quoi.
- **Les erreurs que vous rencontrez** : quand l'application refuse une demande ou tombe en panne, elle note l'opération demandée, le type de l'erreur, sa date et votre compte, jamais ce que vous aviez envoyé ni le message de l'erreur. Il en va de même quand une page de l'application rencontre une erreur dans votre navigateur : celui-ci signale le type de l'erreur, l'écran concerné et l'endroit du programme où elle s'est produite, jamais ce que la page affichait. Ces lignes servent à repérer et à corriger les pannes ; elles sont effacées au bout de {server_error_days} jours. Les administrateurs n'en voient que des totaux, sans savoir quel compte est concerné.
- **Vos questions à l'assistant** : le texte de chaque question que vous lui posez et de sa réponse, sa date, et le volume de texte échangé avec OpenAI. Ils servent à vous réafficher la conversation, à appliquer la limite quotidienne et à améliorer l'aide. Le texte est effacé au bout de {assistant_days} jours ; il n'en reste que des compteurs. Les administrateurs de l'application lisent ces questions et ces réponses sans savoir quel compte les a posées : n'y écrivez rien qui vous désigne.
- **La date de votre dernière utilisation**, au jour près, pour supprimer les comptes qui ne servent plus, et **les jours où vous êtes venu**, pour savoir si l'application sert dans la durée.

L'application n'utilise aucun outil de mesure d'audience ni de publicité. Elle dépose un seul cookie, nécessaire pour maintenir votre connexion. Votre choix de thème, clair ou sombre, est gardé dans votre navigateur et n'est pas envoyé au serveur. L'écran de connexion affiche le bouton « Se connecter avec Google », chargé depuis les serveurs de Google, qui peut déposer ses propres cookies.

## À quoi servent ces données

Uniquement à faire fonctionner le service : vous connecter, chercher des offres, les comparer à votre CV et vous présenter le résultat. Elles ne sont ni vendues, ni utilisées à des fins publicitaires, ni visibles par les autres utilisateurs.

Ce traitement repose sur l'exécution du service que vous demandez en vous connectant ou en ouvrant un essai (article 6.1.b du RGPD) : sans ces données, l'application ne peut ni chercher ni trier d'offres pour vous. L'empreinte de l'adresse IP d'un essai repose, elle, sur l'intérêt légitime de l'exploitant (article 6.1.f) : empêcher qu'un service dont il paie chaque recherche soit utilisé sans limite.

## À qui elles sont transmises

- **Google**, pour la connexion. Ici, c'est Google qui transmet à l'application votre adresse e-mail et les informations de base de votre profil ; l'application ne lui envoie ni votre CV, ni vos recherches, ni vos offres.
- **OpenAI**, pour évaluer les offres. À chaque recherche, le texte de votre CV sans vos coordonnées, vos phrases de recherche et leurs lieux sont envoyés à OpenAI avec le contenu de chaque page d'offre à évaluer.
  Quand vous interrogez l'assistant, votre question et vos derniers échanges avec lui sont envoyés à OpenAI, avec les extraits des textes du site qui servent à y répondre. Votre CV, vos recherches et vos offres n'en font pas partie.
- **Tavily**, pour la recherche web. Seules vos phrases de recherche, avec leur type de contrat et leur lieu, lui sont envoyées, pas votre CV.
- **Fly.io** (Fly.io, Inc., 2261 Market Street #4990, San Francisco, CA 94114, États-Unis), qui héberge l'application et sa base de données, dans la région de Paris.

Quand une recherche échoue ou que l'application tombe en panne, son administrateur peut en être prévenu par le service de notifications ntfy. Ce message ne contient rien qui vous concerne : seulement le type de l'incident et des nombres.

Ces quatre sociétés sont établies aux États-Unis. Les données hébergées par Fly.io restent dans la région de Paris ; les transmissions à OpenAI, Tavily et Google impliquent un transfert de données hors de l'Union européenne. Google et Fly.io adhèrent au cadre de protection des données UE-États-Unis (Data Privacy Framework). Les transferts d'OpenAI hors de l'Union européenne sont encadrés par les clauses contractuelles types de la Commission européenne, prévues par son accord de traitement des données.

## Durée de conservation

Vos données sont conservées tant que vous utilisez l'application. Un compte resté {inactive_months} mois sans utilisation est supprimé automatiquement, avec tout ce qu'il contient : adresse e-mail, CV, recherches, offres, pages écartées, bilans des recherches, journal des pages évaluées, appels au moteur de recherche, erreurs rencontrées, corrections du tri et questions à l'assistant. Vous n'en êtes pas prévenu, l'application n'envoyant aucun e-mail. Un essai sans compte est supprimé de la même façon {trial_days} jours après son ouverture, que vous vous en serviez ou non : passé ce délai, son cookie a expiré et plus personne ne peut y revenir.

À la suppression d'un compte, par vous ou automatiquement, une seule chose est conservée : le total, par mois, de ce que ses recherches et ses questions à l'assistant ont consommé (nombre de recherches, de pages lues et volume de texte échangé avec OpenAI et Tavily). Ces totaux ne portent ni adresse e-mail, ni contenu, ni date précise : ils ne permettent pas de vous identifier, et servent uniquement à connaître le coût du service dans la durée.

Si votre accès est retiré, vous ne pouvez plus vous connecter : votre compte est supprimé au terme de ce même délai, ou plus tôt si vous le demandez. Tant que vous avez accès à l'application, vous pouvez supprimer votre compte vous-même.

Avant certaines mises à jour de l'application, une copie de sauvegarde de la base de données est faite et conservée au même endroit. La suppression d'un compte retire aussi ses données de ces copies.

## Vos droits

Conformément au règlement général sur la protection des données (RGPD), vous pouvez demander l'accès à vos données, leur rectification ou leur suppression, en recevoir une copie dans un format courant (portabilité), et demander la limitation de leur traitement ou vous y opposer, en écrivant à l'adresse indiquée plus haut. Une réponse vous est donnée dans un délai d'un mois. La suppression porte sur l'ensemble de votre compte : adresse e-mail, CV, recherches, offres, pages écartées, bilans des recherches, journal des pages évaluées, appels au moteur de recherche, erreurs rencontrées, corrections du tri et questions à l'assistant.

Vous pouvez supprimer votre compte vous-même, depuis la page « Compte » de l'application : votre adresse e-mail, votre CV, vos recherches, vos offres, les pages écartées, les bilans de vos recherches, le journal des pages évaluées, les appels au moteur de recherche, les erreurs rencontrées, vos corrections du tri et vos questions à l'assistant sont alors effacés immédiatement, sans retour possible. Vous pouvez aussi remplacer votre CV et supprimer vos recherches sans supprimer votre compte. Vous pouvez aussi retirer l'accès de l'application à votre compte Google depuis les paramètres de sécurité de ce compte.

Un essai sans compte ne porte ni nom ni adresse : l'exploitant ne peut pas retrouver le vôtre à partir d'une demande écrite (article 11 du RGPD). Vous exercez vos droits vous-même, depuis le navigateur qui a ouvert l'essai : la page « Compte » en efface tout, immédiatement.

Si vous estimez que vos droits ne sont pas respectés, vous pouvez adresser une réclamation à la CNIL (www.cnil.fr).

## Modifications

Ces règles peuvent évoluer avec l'application. La version en vigueur est celle affichée sur cette page.
