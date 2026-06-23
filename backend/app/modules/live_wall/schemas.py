"""Live Wall preset schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Supported grid dimensions. Must match the frontend's LAYOUTS list.
SUPPORTED_GRIDS: set[tuple[int, int]] = {(1, 1), (2, 2), (3, 3), (4, 4)}

# Type for a tile entry — either a camera UUID or None (empty slot).
TileEntry = UUID | None


class WallPresetBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    rows: Literal[1, 2, 3, 4]
    cols: Literal[1, 2, 3, 4]
    tiles: list[TileEntry] = Field(default_factory=list)
    is_default: bool = False

    @model_validator(mode="after")
    def _validate_grid_and_tiles(self) -> "WallPresetBase":
        # Only supported grid sizes
        if (self.rows, self.cols) not in SUPPORTED_GRIDS:
            raise ValueError(
                f"Unsupported grid {self.rows}x{self.cols}. "
                f"Supported: {sorted(SUPPORTED_GRIDS)}"
            )

        # Tiles length must equal rows*cols (or be empty meaning "all unset")
        expected = self.rows * self.cols
        if len(self.tiles) == 0:
            # Treat empty as "fill with nulls"
            self.tiles = [None] * expected
        elif len(self.tiles) != expected:
            raise ValueError(
                f"tiles must have {expected} entries for a "
                f"{self.rows}x{self.cols} grid, got {len(self.tiles)}"
            )

        # All non-null entries must be unique — same camera can't be in
        # two tiles of the same preset
        seen: set[UUID] = set()
        for entry in self.tiles:
            if entry is None:
                continue
            if entry in seen:
                raise ValueError(
                    f"Camera {entry} appears more than once in tiles"
                )
            seen.add(entry)

        return self


class WallPresetCreate(WallPresetBase):
    pass


class WallPresetUpdate(BaseModel):
    """All fields optional — partial update."""
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    rows: Literal[1, 2, 3, 4] | None = None
    cols: Literal[1, 2, 3, 4] | None = None
    tiles: list[TileEntry] | None = None
    is_default: bool | None = None


class WallPresetRead(WallPresetBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
