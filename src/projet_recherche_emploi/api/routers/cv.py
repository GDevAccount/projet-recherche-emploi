from fastapi import APIRouter, UploadFile

from projet_recherche_emploi.api.security import Services, UserId
from projet_recherche_emploi.schemas import CvStatus
from projet_recherche_emploi.services.cv_service import MAX_CV_BYTES

router = APIRouter(tags=["CV"])


@router.get("/cv")
def get_cv_status(user_id: UserId, services: Services) -> CvStatus:
    return services.cv.get_status(user_id)


@router.put("/cv")
def save_cv(file: UploadFile, user_id: UserId, services: Services) -> CvStatus:
    # Un octet de plus que la limite suffit au service pour refuser, sans lire un fichier énorme en entier
    return services.cv.save_cv(user_id, file.file.read(MAX_CV_BYTES + 1))
