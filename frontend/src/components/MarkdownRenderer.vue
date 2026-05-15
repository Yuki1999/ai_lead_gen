<script setup lang="ts">
import type { MarkdownBlock } from "../markdown";
import InlineMarkdown from "./InlineMarkdown.vue";

defineProps<{
  blocks: MarkdownBlock[];
}>();
</script>

<template>
  <div class="markdown-renderer">
    <template v-for="(block, index) in blocks" :key="index">
      <h2 v-if="block.type === 'heading' && block.level <= 2">
        <InlineMarkdown :tokens="block.content" />
      </h2>
      <h3 v-else-if="block.type === 'heading' && block.level === 3">
        <InlineMarkdown :tokens="block.content" />
      </h3>
      <h4 v-else-if="block.type === 'heading'">
        <InlineMarkdown :tokens="block.content" />
      </h4>
      <p v-else-if="block.type === 'paragraph'">
        <InlineMarkdown :tokens="block.content" />
      </p>
      <blockquote v-else-if="block.type === 'blockquote'">
        <InlineMarkdown :tokens="block.content" />
      </blockquote>
      <ol v-else-if="block.type === 'list' && block.ordered">
        <li v-for="(item, itemIndex) in block.items" :key="itemIndex">
          <InlineMarkdown :tokens="item" />
        </li>
      </ol>
      <ul v-else-if="block.type === 'list'">
        <li v-for="(item, itemIndex) in block.items" :key="itemIndex">
          <InlineMarkdown :tokens="item" />
        </li>
      </ul>
      <div v-else-if="block.type === 'table'" class="markdown-table-scroll">
        <table>
          <thead>
            <tr>
              <th v-for="(cell, cellIndex) in block.headers" :key="cellIndex">
                <InlineMarkdown :tokens="cell" />
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, rowIndex) in block.rows" :key="rowIndex">
              <td v-for="(cell, cellIndex) in row" :key="cellIndex">
                <InlineMarkdown :tokens="cell" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <pre v-else-if="block.type === 'code_block'"><code>{{ block.text }}</code></pre>
      <hr v-else-if="block.type === 'rule'" />
    </template>
  </div>
</template>
