// ImageTile (issue 232): one work in the image-first Shortlist. The image fills the tile at
// its own proportions (a masonry grid); the title shows on hover or keyboard focus in the
// Images view and under the image in the Captions view. Status is on every tile, never
// blank (ADR-026): compact marks, or the full badges if Settings asks for them. Clicking
// the image opens the lightbox. Keep (✓) puts the work on the shortlist.
//
// Images follow the card's rule (showsImage): only works the source states are open, from
// the source's own host. Any other work shows a lock and why, never an image.
import type { BoardItem } from "../api/types";
import type { CardStyle } from "../cardStyle";
import { showsImage } from "./EvidenceCard";
import { Icon } from "./Icon";
import { safeUrl } from "./safeUrl";
import { StatusBadge } from "./StatusBadge";
import { StatusMarks } from "./StatusMarks";
import "./ImageTile.css";

export type Density = "images" | "captions" | "full";

export interface ImageTileProps {
  item: BoardItem;
  density: Exclude<Density, "full">;
  cardStyle: CardStyle;
  onOpen: () => void;
  onKeep?: (keep: boolean) => void; // absent when the shortlist cannot change
}

function Status({ item, cardStyle }: { item: BoardItem; cardStyle: CardStyle }) {
  if (cardStyle === "marks") return <StatusMarks item={item} />;
  return (
    <span className="rd-tile-badges">
      <StatusBadge kind="attribution" status={item.attribution_status} />
      <StatusBadge kind="rights" status={item.record.rights.status} inferred={!item.record.rights.flag_field} />
    </span>
  );
}

export function ImageTile({ item, density, cardStyle, onOpen, onKeep }: ImageTileProps) {
  const { record } = item;
  const title = record.title ?? record.id;
  const maker = [record.artist, record.date].filter(Boolean).join(", ");
  const alt = [record.title, record.artist].filter(Boolean).join(", ") || `Artwork ${record.id}`;
  return (
    <li className={`rd-tile${item.selected ? " rd-tile--kept" : ""}`}>
      <button type="button" className="rd-tile-open" onClick={onOpen} aria-label={`Open ${title}`}>
        {showsImage(item) ? (
          <img src={safeUrl(record.image_url)} alt={alt} loading="lazy" />
        ) : (
          <span className="rd-tile-noimage">
            <Icon name="lock" />
            No image shown: the source does not state this work is open.
          </span>
        )}
        {density === "images" && (
          <span className="rd-tile-hover" aria-hidden="true">
            <strong>{title}</strong>
            {maker && <span>{maker}</span>}
          </span>
        )}
      </button>
      {density === "images" ? (
        <span className="rd-tile-status">
          <Status item={item} cardStyle={cardStyle} />
        </span>
      ) : (
        <span className="rd-tile-caption">
          <strong>{title}</strong>
          {maker && <span className="rd-tile-maker">{maker}</span>}
          <Status item={item} cardStyle={cardStyle} />
        </span>
      )}
      {onKeep && (
        <button
          type="button"
          className="rd-tile-keep"
          aria-pressed={item.selected}
          aria-label={`Keep ${title}`}
          title={item.selected ? "Kept" : "Keep"}
          onClick={() => onKeep(!item.selected)}
        >
          <Icon name="check" />
        </button>
      )}
    </li>
  );
}
