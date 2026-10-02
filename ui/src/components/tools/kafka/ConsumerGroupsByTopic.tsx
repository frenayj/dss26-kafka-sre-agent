// ``list_consumer_groups`` and ``list_consumer_groups_by_topic`` return the
// same item shape and benefit from the same lag-bar layout. The only thing
// "by topic" implies is upstream scoping; the rendered card is identical.
// Single component, single source of truth.
export { ConsumerGroups as ConsumerGroupsByTopic } from "./ConsumerGroups"
