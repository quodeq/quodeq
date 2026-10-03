import {
  FILE_SHAPE_BASE, FILE_X, FILE_Y, FILE_W, FILE_H, FILE_FOLD, FILE_CORNER_RX,
  FILE_BODY_STROKE_PX, FILE_FOLD_STROKE_PX, FILE_FILL_OPACITY, FILE_FOLD_OPACITY, FILE_RULE_LINES, ruleLineColor,
} from './fileShapeGeometry.js';

// Below this on-screen radius the fold and rule lines are sub-pixel noise;
// the page body alone reads as a file.
const DETAIL_MIN_PX = 3;

function traceBody(ctx) {
  const x = FILE_X, y = FILE_Y, w = FILE_W, h = FILE_H, f = FILE_FOLD, rx = FILE_CORNER_RX;
  ctx.beginPath();
  ctx.moveTo(x + rx, y);
  ctx.lineTo(x + w - f, y);
  ctx.lineTo(x + w, y + f);
  ctx.lineTo(x + w, y + h - rx);
  ctx.quadraticCurveTo(x + w, y + h, x + w - rx, y + h);
  ctx.lineTo(x + rx, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - rx);
  ctx.lineTo(x, y + rx);
  ctx.quadraticCurveTo(x, y, x + rx, y);
  ctx.closePath();
}

function traceDetail(ctx, scale, stroke) {
  const x = FILE_X, y = FILE_Y, w = FILE_W, f = FILE_FOLD;
  ctx.beginPath();
  ctx.moveTo(x + w - f, y);
  ctx.lineTo(x + w - f, y + f);
  ctx.lineTo(x + w, y + f);
  ctx.lineWidth = FILE_FOLD_STROKE_PX / scale;
  ctx.strokeStyle = stroke;
  ctx.globalAlpha = FILE_FOLD_OPACITY;
  ctx.stroke();
  ctx.globalAlpha = 1;
  ctx.lineWidth = FILE_BODY_STROKE_PX / scale;
  for (const [x1, ly, x2, opacity] of FILE_RULE_LINES) {
    ctx.beginPath();
    ctx.moveTo(x1, ly);
    ctx.lineTo(x2, ly);
    ctx.strokeStyle = ruleLineColor(opacity);
    ctx.stroke();
  }
}

/** Draw the document icon for a file circle: same page, fold and rule
 * lines as the SVG FileShape, at `px`,`py` pixels with radius `rPx`. */
export function drawFileIcon(ctx, { px, py, rPx, fill, stroke, glow }) {
  const scale = rPx / (FILE_SHAPE_BASE / 2);
  ctx.save();
  ctx.translate(px, py);
  ctx.scale(scale, scale);
  traceBody(ctx);
  if (glow) {
    ctx.shadowColor = stroke;
    ctx.shadowBlur = glow / scale;
  }
  ctx.globalAlpha = FILE_FILL_OPACITY;
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.shadowBlur = 0;
  ctx.globalAlpha = 1;
  ctx.lineWidth = FILE_BODY_STROKE_PX / scale;
  ctx.strokeStyle = stroke;
  ctx.stroke();
  if (rPx >= DETAIL_MIN_PX) traceDetail(ctx, scale, stroke);
  ctx.restore();
}
