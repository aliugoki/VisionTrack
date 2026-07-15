"""Single import point for every ORM model.

Importing this module (anywhere) registers every Camera, Site, User,
Tenant, Role, Track, TrackPoint with SQLAlchemy's mapper registry. This
solves the "forward reference 'Site' failed to locate" error that hits
any process which doesn't transitively load all model modules
(e.g. Celery workers, Alembic in some configurations, ad-hoc scripts).

The imports below look unused — they are not. Each one has the side
effect of declaring its ORM classes against Base.metadata.

Add new model modules here whenever you create one.
"""

from app.modules.tenants import models as _tenants  # noqa: F401
from app.modules.roles import models as _roles  # noqa: F401
from app.modules.users import models as _users  # noqa: F401
from app.modules.sites import models as _sites  # noqa: F401
from app.modules.cameras import models as _cameras  # noqa: F401
from app.modules.tracks import models as _tracks  # noqa: F401
from app.modules.live_wall import models as _live_wall  # noqa: F401
from app.modules.floor_plans import models as _floor_plans  # noqa: F401
from app.modules.alerts import models as _alerts  # noqa: F401
from app.modules.persons import models as _persons  # noqa: F401
from app.modules.mv3dt import models as _mv3dt  # noqa: F401
from app.modules.employees import models as _employees  # noqa: F401
from app.modules.companies import models as _companies  # noqa: F401
