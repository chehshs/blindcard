<?php
/**
 * /tools/ は WordPress の固定ページ。
 * /tools/blindcard/ を実ディレクトリにしたため、親 /tools/ がディレクトリ扱いになり
 * ルートの rewrite を通らない。ここで WP を起動してスラッグ tools を出す。
 */
define( 'WP_USE_THEMES', true );
require dirname( __DIR__ ) . '/wp-blog-header.php';
