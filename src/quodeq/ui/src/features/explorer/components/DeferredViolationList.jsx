import VirtualList from './VirtualList.jsx';
import DeferredMount from './DeferredMount.jsx';
import CardListSkeleton from './CardListSkeleton.jsx';
import { t } from '../../../strings/index.js';
import { rowKeyGetter, rowSizeEstimator } from './findingListRows.js';

/**
 * The violation card list of the file and principle detail pages.
 *
 * Both pages get all their data through nav params, so nothing fetches and
 * without the two-commit split the first paint waits for every visible
 * card's pretext layout effect: the click that navigated here looks ignored.
 * Header first, cards one commit later. `resetKey` remounts the list (and
 * its measurements) when the page's item set changes identity. `rowHeights`
 * sizes the rows (see rowSizeEstimator) and `findingKey(item, index)` keys
 * every non-header row.
 */
export default function DeferredViolationList({ resetKey, items, scrollElement, rowHeights, findingKey, renderItem }) {
  return (
    <DeferredMount fallback={<CardListSkeleton />}>
      <VirtualList
        key={resetKey}
        items={items}
        scrollElement={scrollElement}
        estimateSize={rowSizeEstimator(items, rowHeights)}
        getItemKey={rowKeyGetter(items, findingKey)}
        label={t('explorer.violationsListAria')}
        renderItem={renderItem}
      />
    </DeferredMount>
  );
}
