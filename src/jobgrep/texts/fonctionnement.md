# Comment fonctionne JobGrep

JobGrep est un agent de recherche d'emploi. Il cherche des offres sur les principaux sites, lit chaque annonce à votre place, la compare à votre CV et ne garde que celles qui vous correspondent, avec la raison de son verdict. Vous y suivez ensuite vos candidatures.

C'est un projet personnel, mis à disposition gratuitement. [Ouvrir JobGrep](/)

## 1. Vous déposez votre CV

Vous déposez votre CV en PDF. Vos coordonnées en sont retirées avant toute comparaison : adresse e-mail, téléphone, liens, adresse postale, date de naissance et, quand il est connu, votre nom. Le fichier lui-même n'est pas conservé : seul son texte, sans ces coordonnées, est enregistré.

## 2. Vos postes recherchés sont préparés pour vous

Un modèle d'intelligence artificielle lit votre CV, sans vos coordonnées, et en tire jusqu'à {max_profile_jobs} postes à rechercher, avec leurs compétences, leur contrat et le département ou la région où vous vivez. Vous les retrouvez dans votre profil, où vous pouvez les corriger, les supprimer ou en ajouter à la main.

Pour chaque poste ajouté à la main, vous indiquez le métier, les compétences qui le précisent si vous le souhaitez, le type de contrat (CDI, freelance, CDD, alternance ou stage) et le lieu : une ville, toute la France, ou le télétravail complet. Vous pouvez en décrire plusieurs.

## 3. Vous lancez une recherche

Une recherche prend environ une minute. JobGrep interroge les sites d'emploi, puis un modèle d'intelligence artificielle lit chaque annonce trouvée et relève ce qu'elle dit : le métier, les compétences demandées, le niveau d'expérience, le contrat et le lieu. Une annonce n'est retenue que si tous ces points correspondent à votre CV et à vos postes recherchés.

Vous voyez chaque annonce passer, retenue ou écartée. À la recherche suivante, seules les nouvelles annonces sont lues. Une annonce que vous avez déjà, reprise par un autre site, est reconnue à son texte et écartée sans être relue.

Les sites consultés : {job_sites}. Une recherche en télétravail complet est aussi menée en anglais, sur des sites spécialisés.

## 4. Vous suivez vos candidatures

Les annonces retenues arrivent dans vos offres, avec la raison pour laquelle elles vous correspondent et un lien vers l'annonce d'origine. Pour chacune, vous indiquez où vous en êtes : candidature envoyée, entretien obtenu, refus.

## 5. Vous corrigez le tri quand il se trompe

Les annonces écartées restent consultables, avec leur motif. Si une bonne offre s'y trouve, vous la remettez dans vos offres. Si une offre retenue n'a pas d'intérêt, vous la supprimez en disant pourquoi. Chaque correction sert à mesurer et à améliorer le tri.

## Ce qu'il faut pour commencer

Les écrans de JobGrep se consultent sans compte. Quand il est proposé, un essai sans compte donne droit à {trial_searches} recherche, avec votre CV : il s'ouvre au dépôt du CV, sans rien demander d'autre, et il est supprimé au bout de {trial_days} jours.

La connexion se fait avec un compte Google, qui ne transmet que votre adresse e-mail et votre profil de base. Elle garde votre CV et vos offres, y compris ceux d'un essai si votre compte n'a pas encore de CV. Chaque compte dispose de {max_searches} recherches par jour.

## Vos données

Le texte de votre CV, sans vos coordonnées, est envoyé au modèle qui lit les annonces. Vous pouvez effacer votre compte et tout ce qu'il contient à tout moment, depuis la page « Compte ». Le détail est dans les [règles de confidentialité](/confidentialite) et les [conditions d'utilisation](/conditions).
